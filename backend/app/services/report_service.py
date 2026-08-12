"""Reporting & analytics: role dashboards and downloadable CSV summaries.

All aggregations are live SQL (no cache table yet). Loss ratio is
``claim_payouts / premium_collected`` over a rolling 12-month window.
"""

from __future__ import annotations

import csv
import io
import uuid
from calendar import monthrange
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import Select, and_, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import Date as SADate

from app.core.exceptions import ForbiddenError
from app.models.audit import AuditLog
from app.models.billing import Payment, PremiumSchedule
from app.models.claim import Claim
from app.models.customer import Customer
from app.models.enums import (
    ClaimStatus,
    PaymentStatus,
    PaymentType,
    PolicyStatus,
    PolicyType,
    PremiumScheduleStatus,
    QuoteStatus,
    UserRole,
)
from app.models.policy import Policy
from app.models.quote import Quote
from app.models.user import User
from app.schemas.report import (
    AdjusterDashboard,
    AdjusterQueueItem,
    AgentActivityItem,
    AgentDashboard,
    AgentProductionRow,
    CustomerClaimCard,
    CustomerDashboard,
    CustomerPaymentCard,
    CustomerPolicyCard,
    LossRatioRow,
    ManagerDashboard,
    MonthCount,
    NamedCount,
)

ZERO = Decimal("0.00")
MONEY_Q = Decimal("0.01")

OPEN_CLAIM_STATUSES: frozenset[ClaimStatus] = frozenset(
    {
        ClaimStatus.submitted,
        ClaimStatus.assigned,
        ClaimStatus.investigating,
        ClaimStatus.info_requested,
        ClaimStatus.approved,
        ClaimStatus.disputed,
    }
)
CLOSED_CLAIM_STATUSES: frozenset[ClaimStatus] = frozenset(
    {ClaimStatus.closed, ClaimStatus.paid}
)

# Spec doesn't store an info-request deadline; treat 14 days from last update
# as the SLA clock managers/adjusters expect to see.
INFO_REQUEST_SLA_DAYS = 14

_POLICY_TYPE_LABELS = {
    PolicyType.auto: "Auto",
    PolicyType.home: "Home",
    PolicyType.life: "Life",
}


def month_start(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, months: int) -> date:
    """Shift a date by whole months, clamping the day to the target month."""
    year = d.year + (d.month - 1 + months) // 12
    month = (d.month - 1 + months) % 12 + 1
    day = min(d.day, monthrange(year, month)[1])
    return date(year, month, day)


def month_end(d: date) -> date:
    return d.replace(day=monthrange(d.year, d.month)[1])


def compute_loss_ratio(
    premium_collected: Decimal, claims_paid: Decimal
) -> Decimal | None:
    if premium_collected <= ZERO:
        return None
    return (claims_paid / premium_collected).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )


def _money(value: Any) -> Decimal:
    if value is None:
        return ZERO
    return Decimal(str(value)).quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _days_between(start: datetime | date, end: datetime | date) -> float:
    if isinstance(start, datetime):
        start_d = start.astimezone(UTC).date() if start.tzinfo else start.date()
    else:
        start_d = start
    if isinstance(end, datetime):
        end_d = end.astimezone(UTC).date() if end.tzinfo else end.date()
    else:
        end_d = end
    return float((end_d - start_d).days)


# --------------------------------------------------------------------------- #
# Manager
# --------------------------------------------------------------------------- #
async def manager_dashboard(
    db: AsyncSession, *, today: date | None = None
) -> ManagerDashboard:
    today = today or date.today()
    this_month = month_start(today)
    last_month = month_start(add_months(this_month, -1))
    next_month = month_start(add_months(this_month, 1))
    window_start = add_months(this_month, -11)

    active_total = int(
        await db.scalar(
            select(func.count())
            .select_from(Policy)
            .where(Policy.status == PolicyStatus.active)
        )
        or 0
    )

    by_type_rows = (
        await db.execute(
            select(Policy.policy_type, func.count())
            .where(Policy.status == PolicyStatus.active)
            .group_by(Policy.policy_type)
        )
    ).all()
    active_by_type = [
        NamedCount(
            key=pt.value,
            label=_POLICY_TYPE_LABELS.get(pt, pt.value),
            count=int(cnt),
        )
        for pt, cnt in by_type_rows
    ]

    new_this = int(
        await db.scalar(
            select(func.count())
            .select_from(Policy)
            .where(
                cast(Policy.created_at, SADate) >= this_month,
                cast(Policy.created_at, SADate) < next_month,
            )
        )
        or 0
    )
    new_last = int(
        await db.scalar(
            select(func.count())
            .select_from(Policy)
            .where(
                cast(Policy.created_at, SADate) >= last_month,
                cast(Policy.created_at, SADate) < this_month,
            )
        )
        or 0
    )

    sparkline = await _new_policies_sparkline(db, window_start, today)

    open_claims = int(
        await db.scalar(
            select(func.count())
            .select_from(Claim)
            .where(Claim.status.in_(OPEN_CLAIM_STATUSES))
        )
        or 0
    )

    avg_days = await _avg_days_to_close(db)

    premium_12m, payouts_12m = await _premium_and_payouts(
        db, since=add_months(this_month, -12), until=next_month
    )
    loss_ratio = compute_loss_ratio(premium_12m, payouts_12m)

    premium_mtd = await _sum_premium_collected(db, since=this_month, until=next_month)
    # Target ≈ sum of installment amounts due in the month (paid + unpaid).
    target_mtd = _money(
        await db.scalar(
            select(func.coalesce(func.sum(PremiumSchedule.amount_due), 0)).where(
                PremiumSchedule.due_date >= this_month,
                PremiumSchedule.due_date < next_month,
                PremiumSchedule.status != PremiumScheduleStatus.waived,
            )
        )
    )

    top_agents = await _top_agents(db, limit=5)
    claims_by_status = await _claims_by_status(db)
    overdue = int(
        await db.scalar(
            select(func.count())
            .select_from(PremiumSchedule)
            .where(PremiumSchedule.status == PremiumScheduleStatus.overdue)
        )
        or 0
    )

    return ManagerDashboard(
        active_policies_total=active_total,
        active_policies_by_type=active_by_type,
        new_policies_this_month=new_this,
        new_policies_last_month=new_last,
        new_policies_sparkline=sparkline,
        open_claims=open_claims,
        avg_days_to_close=avg_days,
        loss_ratio_12m=loss_ratio,
        premium_collected_mtd=premium_mtd,
        premium_target_mtd=target_mtd,
        top_agents=top_agents,
        claims_by_status=claims_by_status,
        payments_overdue=overdue,
    )


async def _new_policies_sparkline(
    db: AsyncSession, window_start: date, today: date
) -> list[MonthCount]:
    # Twelve month buckets ending with the current month.
    buckets: list[date] = []
    cursor = month_start(window_start)
    end = month_start(today)
    while cursor <= end:
        buckets.append(cursor)
        cursor = add_months(cursor, 1)

    rows = (
        await db.execute(
            select(
                func.date_trunc("month", Policy.created_at).label("month"),
                func.count(),
            )
            .where(cast(Policy.created_at, SADate) >= window_start)
            .group_by("month")
            .order_by("month")
        )
    ).all()
    counted = {
        (m.date() if isinstance(m, datetime) else m).strftime("%Y-%m"): int(c)
        for m, c in rows
        if m is not None
    }
    return [
        MonthCount(month=b.strftime("%Y-%m"), count=counted.get(b.strftime("%Y-%m"), 0))
        for b in buckets
    ]


async def _avg_days_to_close(
    db: AsyncSession, *, adjuster_id: uuid.UUID | None = None
) -> float | None:
    stmt = select(Claim.created_at, Claim.updated_at).where(
        Claim.status.in_(CLOSED_CLAIM_STATUSES)
    )
    if adjuster_id is not None:
        stmt = stmt.where(Claim.adjuster_id == adjuster_id)
    rows = (await db.execute(stmt)).all()
    if not rows:
        return None
    total = sum(_days_between(created, updated) for created, updated in rows)
    return round(total / len(rows), 1)


async def _sum_premium_collected(
    db: AsyncSession, *, since: date, until: date
) -> Decimal:
    return _money(
        await db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.payment_type == PaymentType.premium,
                Payment.status == PaymentStatus.completed,
                cast(Payment.processed_at, SADate) >= since,
                cast(Payment.processed_at, SADate) < until,
            )
        )
    )


async def _sum_claim_payouts(
    db: AsyncSession, *, since: date, until: date
) -> Decimal:
    return _money(
        await db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.payment_type == PaymentType.claim_payout,
                Payment.status == PaymentStatus.completed,
                cast(Payment.processed_at, SADate) >= since,
                cast(Payment.processed_at, SADate) < until,
            )
        )
    )


async def _premium_and_payouts(
    db: AsyncSession, *, since: date, until: date
) -> tuple[Decimal, Decimal]:
    premium = await _sum_premium_collected(db, since=since, until=until)
    payouts = await _sum_claim_payouts(db, since=since, until=until)
    return premium, payouts


async def _top_agents(db: AsyncSession, *, limit: int = 5) -> list[AgentProductionRow]:
    rows = (
        await db.execute(
            select(
                User.id,
                User.first_name,
                User.last_name,
                func.count(Policy.id),
                func.coalesce(func.sum(Policy.annual_premium), 0),
            )
            .join(Policy, Policy.agent_id == User.id)
            .where(User.role == UserRole.agent)
            .group_by(User.id, User.first_name, User.last_name)
            .order_by(func.count(Policy.id).desc())
            .limit(limit)
        )
    ).all()
    return [
        AgentProductionRow(
            agent_id=uid,
            agent_name=f"{first} {last}".strip(),
            policies_written=int(cnt),
            annual_premium=_money(premium),
        )
        for uid, first, last, cnt, premium in rows
    ]


async def _claims_by_status(db: AsyncSession) -> list[NamedCount]:
    rows = (
        await db.execute(
            select(Claim.status, func.count()).group_by(Claim.status)
        )
    ).all()
    return [
        NamedCount(key=status.value, label=status.value.replace("_", " "), count=int(cnt))
        for status, cnt in rows
    ]


# --------------------------------------------------------------------------- #
# Agent
# --------------------------------------------------------------------------- #
async def agent_dashboard(
    db: AsyncSession, actor: User, *, today: date | None = None
) -> AgentDashboard:
    if actor.role not in {UserRole.agent, UserRole.manager, UserRole.super_admin}:
        raise ForbiddenError("Agent dashboard is not available for this role.")
    today = today or date.today()
    this_month = month_start(today)
    next_month = month_start(add_months(this_month, 1))
    in_30 = today + timedelta(days=30)

    # Book = customers linked via policies or quotes written by this agent.
    book = (
        select(Policy.customer_id.label("customer_id"))
        .where(Policy.agent_id == actor.id)
        .union(
            select(Quote.customer_id.label("customer_id")).where(
                Quote.agent_id == actor.id
            )
        )
        .subquery()
    )

    customers_total = int(
        await db.scalar(select(func.count()).select_from(book)) or 0
    )
    customers_new = int(
        await db.scalar(
            select(func.count())
            .select_from(Customer)
            .where(
                Customer.id.in_(select(book.c.customer_id)),
                cast(Customer.created_at, SADate) >= this_month,
                cast(Customer.created_at, SADate) < next_month,
            )
        )
        or 0
    )

    policies_active = int(
        await db.scalar(
            select(func.count())
            .select_from(Policy)
            .where(
                Policy.agent_id == actor.id,
                Policy.status == PolicyStatus.active,
            )
        )
        or 0
    )
    expiring = int(
        await db.scalar(
            select(func.count())
            .select_from(Policy)
            .where(
                Policy.agent_id == actor.id,
                Policy.status == PolicyStatus.active,
                Policy.expiration_date >= today,
                Policy.expiration_date <= in_30,
            )
        )
        or 0
    )
    pending_quotes = int(
        await db.scalar(
            select(func.count())
            .select_from(Quote)
            .where(
                Quote.agent_id == actor.id,
                Quote.status == QuoteStatus.pending_review,
            )
        )
        or 0
    )

    policy_ids = select(Policy.id).where(Policy.agent_id == actor.id)
    activity_rows = (
        await db.execute(
            select(AuditLog)
            .where(
                (AuditLog.actor_id == actor.id)
                | and_(
                    AuditLog.entity_type == "policy",
                    AuditLog.entity_id.in_(policy_ids),
                )
            )
            .order_by(AuditLog.created_at.desc())
            .limit(20)
        )
    ).scalars().all()

    activity = [
        AgentActivityItem(
            id=row.id,
            action=row.action,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            created_at=row.created_at,
            summary=_activity_summary(row),
        )
        for row in activity_rows
    ]

    return AgentDashboard(
        customers_total=customers_total,
        customers_new_this_month=customers_new,
        policies_active=policies_active,
        policies_expiring_30d=expiring,
        pending_quote_approvals=pending_quotes,
        recent_activity=activity,
    )


def _activity_summary(row: AuditLog) -> str | None:
    if row.new_value and isinstance(row.new_value, dict):
        status = row.new_value.get("status")
        if status:
            return f"{row.action} → {status}"
    return row.action


# --------------------------------------------------------------------------- #
# Adjuster
# --------------------------------------------------------------------------- #
async def adjuster_dashboard(
    db: AsyncSession, actor: User, *, today: date | None = None
) -> AdjusterDashboard:
    if actor.role not in {
        UserRole.adjuster,
        UserRole.manager,
        UserRole.super_admin,
    }:
        raise ForbiddenError("Adjuster dashboard is not available for this role.")
    today = today or date.today()
    this_month = month_start(today)
    next_month = month_start(add_months(this_month, 1))

    open_statuses = [
        ClaimStatus.assigned,
        ClaimStatus.investigating,
        ClaimStatus.info_requested,
        ClaimStatus.approved,
        ClaimStatus.disputed,
    ]
    # Managers/admins see the whole queue; adjusters see only their assignments.
    queue_stmt = (
        select(Claim)
        .where(Claim.status.in_(open_statuses))
        .order_by(
            Claim.fraud_flag.desc(),
            Claim.created_at.asc(),
            case(
                (Claim.estimated_damage.is_(None), 0),
                else_=Claim.estimated_damage,
            ).desc(),
        )
    )
    if actor.role == UserRole.adjuster:
        queue_stmt = queue_stmt.where(Claim.adjuster_id == actor.id)
    rows = (await db.execute(queue_stmt)).scalars().all()

    queue = [_to_queue_item(c, today) for c in rows]
    awaiting = [item for item in queue if item.status == ClaimStatus.info_requested]

    personal_id = actor.id if actor.role == UserRole.adjuster else None
    personal_avg = await _avg_days_to_close(db, adjuster_id=personal_id)
    team_avg = await _avg_days_to_close(db)

    closed_stmt = (
        select(func.count())
        .select_from(Claim)
        .where(
            Claim.status.in_(CLOSED_CLAIM_STATUSES),
            cast(Claim.updated_at, SADate) >= this_month,
            cast(Claim.updated_at, SADate) < next_month,
        )
    )
    if actor.role == UserRole.adjuster:
        closed_stmt = closed_stmt.where(Claim.adjuster_id == actor.id)
    closed_mtd = int(await db.scalar(closed_stmt) or 0)

    return AdjusterDashboard(
        assigned_queue=queue,
        awaiting_info=awaiting,
        avg_days_to_resolution_personal=personal_avg,
        avg_days_to_resolution_team=team_avg,
        claims_closed_this_month=closed_mtd,
    )


def _to_queue_item(claim: Claim, today: date) -> AdjusterQueueItem:
    age = int(_days_between(claim.created_at, today))
    days_left = None
    if claim.status == ClaimStatus.info_requested:
        deadline = claim.updated_at.astimezone(UTC).date() + timedelta(
            days=INFO_REQUEST_SLA_DAYS
        )
        days_left = (deadline - today).days
    return AdjusterQueueItem(
        id=claim.id,
        claim_number=claim.claim_number,
        status=claim.status,
        fraud_flag=claim.fraud_flag,
        estimated_damage=claim.estimated_damage,
        created_at=claim.created_at,
        age_days=age,
        days_info_remaining=days_left,
    )


# --------------------------------------------------------------------------- #
# Customer
# --------------------------------------------------------------------------- #
async def customer_dashboard(
    db: AsyncSession, actor: User, *, today: date | None = None
) -> CustomerDashboard:
    if actor.role != UserRole.customer:
        raise ForbiddenError("Customer dashboard is not available for this role.")
    today = today or date.today()

    customer = await db.scalar(select(Customer).where(Customer.user_id == actor.id))
    if customer is None:
        return CustomerDashboard(
            active_policies=[],
            open_claims=[],
            recent_payments=[],
            unread_notifications=0,
        )

    policies = (
        await db.scalars(
            select(Policy)
            .where(
                Policy.customer_id == customer.id,
                Policy.status == PolicyStatus.active,
            )
            .order_by(Policy.effective_date.desc())
        )
    ).all()

    policy_cards: list[CustomerPolicyCard] = []
    for policy in policies:
        next_due = await db.scalar(
            select(PremiumSchedule)
            .where(
                PremiumSchedule.policy_id == policy.id,
                PremiumSchedule.status.in_(
                    {
                        PremiumScheduleStatus.upcoming,
                        PremiumScheduleStatus.due,
                        PremiumScheduleStatus.overdue,
                    }
                ),
            )
            .order_by(PremiumSchedule.due_date.asc())
            .limit(1)
        )
        policy_cards.append(
            CustomerPolicyCard(
                id=policy.id,
                policy_number=policy.policy_number,
                policy_type=policy.policy_type,
                status=policy.status.value,
                next_payment_date=next_due.due_date if next_due else None,
                next_payment_amount=next_due.amount_due if next_due else None,
            )
        )

    claims = (
        await db.scalars(
            select(Claim)
            .where(
                Claim.customer_id == customer.id,
                Claim.status.in_(OPEN_CLAIM_STATUSES),
            )
            .order_by(Claim.created_at.desc())
            .limit(10)
        )
    ).all()
    claim_cards = [
        CustomerClaimCard(
            id=c.id,
            claim_number=c.claim_number,
            status=c.status,
            incident_date=c.incident_date,
            estimated_damage=c.estimated_damage,
        )
        for c in claims
    ]

    payments = (
        await db.scalars(
            select(Payment)
            .where(Payment.customer_id == customer.id)
            .order_by(Payment.created_at.desc())
            .limit(5)
        )
    ).all()
    payment_cards = [
        CustomerPaymentCard(
            id=p.id,
            amount=p.amount,
            status=p.status.value,
            payment_type=p.payment_type.value,
            processed_at=p.processed_at,
            reference_number=p.reference_number,
        )
        for p in payments
    ]

    from app.models.notification import Notification

    unread = int(
        await db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.user_id == actor.id,
                Notification.is_read.is_(False),
            )
        )
        or 0
    )

    return CustomerDashboard(
        active_policies=policy_cards,
        open_claims=claim_cards,
        recent_payments=payment_cards,
        unread_notifications=unread,
    )


# --------------------------------------------------------------------------- #
# CSV reports
# --------------------------------------------------------------------------- #
async def loss_ratio_by_line(
    db: AsyncSession, *, today: date | None = None
) -> list[LossRatioRow]:
    today = today or date.today()
    since = add_months(month_start(today), -12)
    until = month_start(add_months(month_start(today), 1))

    premium_rows = (
        await db.execute(
            select(
                Policy.policy_type,
                func.coalesce(func.sum(Payment.amount), 0),
            )
            .select_from(Payment)
            .join(PremiumSchedule, PremiumSchedule.id == Payment.schedule_id)
            .join(Policy, Policy.id == PremiumSchedule.policy_id)
            .where(
                Payment.payment_type == PaymentType.premium,
                Payment.status == PaymentStatus.completed,
                cast(Payment.processed_at, SADate) >= since,
                cast(Payment.processed_at, SADate) < until,
            )
            .group_by(Policy.policy_type)
        )
    ).all()
    premium_map = {pt: _money(amt) for pt, amt in premium_rows}

    payout_rows = (
        await db.execute(
            select(
                Policy.policy_type,
                func.coalesce(func.sum(Payment.amount), 0),
            )
            .select_from(Payment)
            .join(Claim, Claim.id == Payment.claim_id)
            .join(Policy, Policy.id == Claim.policy_id)
            .where(
                Payment.payment_type == PaymentType.claim_payout,
                Payment.status == PaymentStatus.completed,
                cast(Payment.processed_at, SADate) >= since,
                cast(Payment.processed_at, SADate) < until,
            )
            .group_by(Policy.policy_type)
        )
    ).all()
    payout_map = {pt: _money(amt) for pt, amt in payout_rows}

    rows: list[LossRatioRow] = []
    for pt in PolicyType:
        premium = premium_map.get(pt, ZERO)
        paid = payout_map.get(pt, ZERO)
        rows.append(
            LossRatioRow(
                policy_type=pt,
                premium_collected=premium,
                claims_paid=paid,
                loss_ratio=compute_loss_ratio(premium, paid),
            )
        )
    return rows


def _csv_from_rows(headers: list[str], rows: list[list[Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


async def export_claims_summary_csv(
    db: AsyncSession,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    status: ClaimStatus | None = None,
) -> str:
    stmt: Select = (
        select(
            Claim.claim_number,
            Claim.status,
            Claim.claim_type,
            Claim.incident_date,
            Claim.reported_date,
            Claim.estimated_damage,
            Claim.approved_amount,
            Claim.final_payout,
            Claim.fraud_flag,
            Policy.policy_number,
            Policy.policy_type,
        )
        .join(Policy, Policy.id == Claim.policy_id)
        .order_by(Claim.created_at.desc())
    )
    if date_from is not None:
        stmt = stmt.where(Claim.reported_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Claim.reported_date <= date_to)
    if status is not None:
        stmt = stmt.where(Claim.status == status)

    rows = (await db.execute(stmt.limit(10_000))).all()
    return _csv_from_rows(
        [
            "claim_number",
            "status",
            "claim_type",
            "incident_date",
            "reported_date",
            "estimated_damage",
            "approved_amount",
            "final_payout",
            "fraud_flag",
            "policy_number",
            "policy_type",
        ],
        [
            [
                r.claim_number,
                r.status.value,
                r.claim_type.value,
                r.incident_date.isoformat(),
                r.reported_date.isoformat(),
                r.estimated_damage or "",
                r.approved_amount or "",
                r.final_payout or "",
                r.fraud_flag,
                r.policy_number,
                r.policy_type.value,
            ]
            for r in rows
        ],
    )


async def export_billing_summary_csv(
    db: AsyncSession, *, today: date | None = None
) -> str:
    today = today or date.today()
    this_month = month_start(today)
    next_month = month_start(add_months(this_month, 1))

    rows = (
        await db.execute(
            select(
                Policy.policy_number,
                Policy.policy_type,
                Policy.status.label("policy_status"),
                PremiumSchedule.due_date,
                PremiumSchedule.amount_due,
                PremiumSchedule.status.label("schedule_status"),
            )
            .join(Policy, Policy.id == PremiumSchedule.policy_id)
            .where(
                PremiumSchedule.due_date >= this_month,
                PremiumSchedule.due_date < next_month,
            )
            .order_by(PremiumSchedule.due_date.asc())
            .limit(10_000)
        )
    ).all()
    return _csv_from_rows(
        [
            "policy_number",
            "policy_type",
            "policy_status",
            "due_date",
            "amount_due",
            "schedule_status",
        ],
        [
            [
                number,
                ptype.value,
                pstatus.value,
                due.isoformat(),
                amount,
                sstatus.value,
            ]
            for number, ptype, pstatus, due, amount, sstatus in rows
        ],
    )


async def export_loss_ratio_csv(db: AsyncSession) -> str:
    rows = await loss_ratio_by_line(db)
    return _csv_from_rows(
        ["policy_type", "premium_collected", "claims_paid", "loss_ratio"],
        [
            [
                r.policy_type.value,
                r.premium_collected,
                r.claims_paid,
                r.loss_ratio if r.loss_ratio is not None else "",
            ]
            for r in rows
        ],
    )


async def export_agent_production_csv(db: AsyncSession) -> str:
    rows = await _top_agents(db, limit=10_000)
    return _csv_from_rows(
        ["agent_id", "agent_name", "policies_written", "annual_premium"],
        [
            [str(r.agent_id), r.agent_name, r.policies_written, r.annual_premium]
            for r in rows
        ],
    )


async def export_customer_policy_history_csv(
    db: AsyncSession, customer_id: uuid.UUID
) -> str:
    rows = (
        await db.execute(
            select(
                Policy.policy_number,
                Policy.policy_type,
                Policy.status,
                Policy.effective_date,
                Policy.expiration_date,
                Policy.annual_premium,
                User.first_name,
                User.last_name,
            )
            .outerjoin(User, User.id == Policy.agent_id)
            .where(Policy.customer_id == customer_id)
            .order_by(Policy.effective_date.desc())
        )
    ).all()
    return _csv_from_rows(
        [
            "policy_number",
            "policy_type",
            "status",
            "effective_date",
            "expiration_date",
            "annual_premium",
            "agent",
        ],
        [
            [
                number,
                ptype.value,
                status.value,
                effective.isoformat(),
                expiration.isoformat(),
                premium,
                f"{first or ''} {last or ''}".strip(),
            ]
            for number, ptype, status, effective, expiration, premium, first, last in rows
        ],
    )
