"""Policy binding, numbering, premium schedules, and cancellation."""

from __future__ import annotations

import calendar
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, ForbiddenError, NotFoundError
from app.models.billing import PremiumSchedule
from app.models.customer import Customer
from app.models.enums import (
    NotificationType,
    PaymentFrequency,
    PolicyStatus,
    PolicyType,
    PremiumScheduleStatus,
    QuoteStatus,
    UserRole,
)
from app.models.policy import (
    Beneficiary,
    Policy,
    PolicyAutoDetails,
    PolicyHomeDetails,
    PolicyLifeDetails,
)
from app.models.quote import Quote
from app.models.user import User
from app.schemas.policy import (
    BeneficiaryRead,
    PolicyListItem,
    PolicyRead,
    PremiumScheduleRead,
)
from app.services import audit_service, billing, notification_service

_CENTS = Decimal("0.01")

_FREQUENCY_INSTALLMENTS: dict[PaymentFrequency, int] = {
    PaymentFrequency.monthly: 12,
    PaymentFrequency.quarterly: 4,
    PaymentFrequency.semi_annual: 2,
    PaymentFrequency.annual: 1,
}

_FREQUENCY_MONTHS: dict[PaymentFrequency, int] = {
    PaymentFrequency.monthly: 1,
    PaymentFrequency.quarterly: 3,
    PaymentFrequency.semi_annual: 6,
    PaymentFrequency.annual: 12,
}

_SEQ_BY_TYPE: dict[PolicyType, str] = {
    PolicyType.auto: "policy_number_auto",
    PolicyType.home: "policy_number_home",
    PolicyType.life: "policy_number_life",
}


def _add_months(d: date, months: int) -> date:
    """Add calendar months, clamping the day to the target month's length."""
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def build_policy_number(policy_type: PolicyType, year: int, seq: int) -> str:
    """Format: ``{TYPE}-{YEAR}-{6-digit-seq}`` e.g. ``AUTO-2026-000123``."""
    return f"{policy_type.value.upper()}-{year}-{seq:06d}"


def generate_premium_schedule_rows(
    *,
    annual_premium: Decimal,
    payment_frequency: PaymentFrequency,
    effective_date: date,
) -> list[tuple[date, Decimal]]:
    """Return ``(due_date, amount)`` rows for one policy term."""
    installments = _FREQUENCY_INSTALLMENTS[payment_frequency]
    months = _FREQUENCY_MONTHS[payment_frequency]
    per = (annual_premium / Decimal(installments)).quantize(
        _CENTS, rounding=ROUND_HALF_UP
    )
    # Absorb rounding remainder on the final installment.
    amounts = [per] * installments
    amounts[-1] = (annual_premium - per * (installments - 1)).quantize(
        _CENTS, rounding=ROUND_HALF_UP
    )

    rows: list[tuple[date, Decimal]] = []
    for i, amount in enumerate(amounts):
        due = _add_months(effective_date, months * i)
        rows.append((due, amount))
    return rows


async def next_policy_number(db: AsyncSession, policy_type: PolicyType) -> str:
    seq_name = _SEQ_BY_TYPE[policy_type]
    result = await db.execute(text(f"SELECT nextval('{seq_name}')"))
    seq = int(result.scalar_one())
    year = datetime.now(UTC).year
    return build_policy_number(policy_type, year, seq)


def _expiration_date(effective: date) -> date:
    return _add_months(effective, 12) - timedelta(days=1)


async def bind_quote(
    db: AsyncSession,
    quote_id: uuid.UUID,
    actor: User,
    payment_frequency: PaymentFrequency = PaymentFrequency.monthly,
) -> Policy:
    quote = await db.scalar(select(Quote).where(Quote.id == quote_id))
    if quote is None:
        raise NotFoundError("Quote not found.", code="QUOTE_NOT_FOUND")
    if quote.status != QuoteStatus.approved:
        raise AppError(
            "Only approved quotes can be bound.",
            code="QUOTE_NOT_APPROVED",
            status_code=409,
        )
    if quote.expiry_date and quote.expiry_date < date.today():
        quote.status = QuoteStatus.expired
        await db.commit()
        raise AppError("Quote has expired.", code="QUOTE_EXPIRED", status_code=409)
    if quote.quoted_premium is None or quote.effective_date is None:
        raise AppError("Quote is missing premium or effective date.", code="QUOTE_INCOMPLETE")
    if not quote.policy_details:
        raise AppError("Quote is missing policy details.", code="QUOTE_INCOMPLETE")

    policy_number = await next_policy_number(db, quote.policy_type)
    effective = quote.effective_date
    policy = Policy(
        policy_number=policy_number,
        customer_id=quote.customer_id,
        quote_id=quote.id,
        policy_type=quote.policy_type,
        status=PolicyStatus.active,
        effective_date=effective,
        expiration_date=_expiration_date(effective),
        annual_premium=quote.quoted_premium,
        payment_frequency=payment_frequency,
        agent_id=actor.id if actor.role != UserRole.customer else quote.agent_id,
        underwriter_id=quote.underwriter_id,
    )
    db.add(policy)
    await db.flush()

    await _persist_details(db, policy, quote)
    await _create_premium_schedules(db, policy)

    quote.status = QuoteStatus.bound
    notif = await notification_service.notify_customer(
        db,
        policy.customer_id,
        notification_type=NotificationType.general,
        title="Policy bound",
        body=(
            f"Policy {policy.policy_number} is now active. Your declaration "
            f"page will be available under Documents shortly."
        ),
        related_entity_type="policy",
        related_entity_id=policy.id,
    )
    await db.commit()
    if notif:
        notification_service.queue_email(notif.id)
    return await get_policy(db, policy.id)


async def _persist_details(db: AsyncSession, policy: Policy, quote: Quote) -> None:
    details = quote.policy_details or {}
    if policy.policy_type == PolicyType.auto:
        db.add(
            PolicyAutoDetails(
                policy_id=policy.id,
                vin=details["vin"],
                make=details.get("make"),
                model=details.get("model"),
                year=details.get("year"),
                vehicle_type=details.get("vehicle_type"),
                primary_use=details.get("primary_use"),
                annual_mileage=details.get("annual_mileage"),
                garaging_zip=details.get("garaging_zip"),
                coverage_type=details.get("coverage_type"),
                liability_limit=details.get("liability_limit"),
                collision_deductible=details.get("collision_deductible"),
                comprehensive_deductible=details.get("comprehensive_deductible"),
                uninsured_motorist=bool(details.get("uninsured_motorist", False)),
                roadside_assistance=bool(details.get("roadside_assistance", False)),
                rental_reimbursement=bool(details.get("rental_reimbursement", False)),
            )
        )
    elif policy.policy_type == PolicyType.home:
        db.add(
            PolicyHomeDetails(
                policy_id=policy.id,
                property_address_line1=details.get("property_address_line1"),
                property_address_line2=details.get("property_address_line2"),
                city=details.get("city"),
                state=details.get("state"),
                zip=details.get("zip"),
                year_built=details.get("year_built"),
                square_footage=details.get("square_footage"),
                construction_type=details.get("construction_type"),
                roof_type=details.get("roof_type"),
                roof_year=details.get("roof_year"),
                home_value=details.get("home_value"),
                dwelling_coverage=details.get("dwelling_coverage"),
                personal_property_coverage=details.get("personal_property_coverage"),
                liability_coverage=details.get("liability_coverage"),
                deductible=details.get("deductible"),
                flood_coverage=bool(details.get("flood_coverage", False)),
                earthquake_coverage=bool(details.get("earthquake_coverage", False)),
                home_business_coverage=bool(details.get("home_business_coverage", False)),
            )
        )
    elif policy.policy_type == PolicyType.life:
        db.add(
            PolicyLifeDetails(
                policy_id=policy.id,
                coverage_amount=details["coverage_amount"],
                policy_term_years=details.get("policy_term_years"),
                life_type=details.get("life_type"),
                tobacco_user=bool(details.get("tobacco_user", False)),
                health_class=details.get("health_class"),
                premium_mode=details.get("premium_mode"),
            )
        )
        for ben in details.get("beneficiaries") or []:
            dob = ben.get("date_of_birth")
            if isinstance(dob, str):
                dob = date.fromisoformat(dob)
            db.add(
                Beneficiary(
                    policy_id=policy.id,
                    full_name=ben["full_name"],
                    relationship_type=ben.get("relationship"),
                    allocation_pct=ben["allocation_pct"],
                    ssn_last4=ben.get("ssn_last4"),
                    date_of_birth=dob,
                    is_contingent=bool(ben.get("is_contingent", False)),
                )
            )


async def _create_premium_schedules(db: AsyncSession, policy: Policy) -> None:
    rows = generate_premium_schedule_rows(
        annual_premium=policy.annual_premium,
        payment_frequency=policy.payment_frequency,
        effective_date=policy.effective_date,
    )
    today = date.today()
    for due_date, amount in rows:
        status = (
            PremiumScheduleStatus.due
            if due_date <= today
            else PremiumScheduleStatus.upcoming
        )
        db.add(
            PremiumSchedule(
                policy_id=policy.id,
                due_date=due_date,
                amount_due=amount,
                status=status,
            )
        )


async def get_policy(db: AsyncSession, policy_id: uuid.UUID) -> Policy:
    policy = await db.scalar(select(Policy).where(Policy.id == policy_id))
    if policy is None:
        raise NotFoundError("Policy not found.", code="POLICY_NOT_FOUND")
    return policy


async def assert_policy_access(db: AsyncSession, policy: Policy, actor: User) -> None:
    if actor.role in {
        UserRole.agent,
        UserRole.manager,
        UserRole.super_admin,
        UserRole.adjuster,
    }:
        return
    if actor.role == UserRole.customer:
        customer = await db.scalar(select(Customer).where(Customer.user_id == actor.id))
        if customer is not None and customer.id == policy.customer_id:
            return
    raise ForbiddenError("You do not have access to this policy.")


async def list_policies(
    db: AsyncSession,
    actor: User,
    *,
    page: int,
    per_page: int,
    status: PolicyStatus | None = None,
    policy_type: PolicyType | None = None,
    customer_id: uuid.UUID | None = None,
) -> tuple[list[Policy], int]:
    stmt = select(Policy)
    count_stmt = select(func.count(Policy.id))

    if actor.role == UserRole.customer:
        customer = await db.scalar(select(Customer).where(Customer.user_id == actor.id))
        if customer is None:
            return [], 0
        stmt = stmt.where(Policy.customer_id == customer.id)
        count_stmt = count_stmt.where(Policy.customer_id == customer.id)
    elif customer_id is not None:
        stmt = stmt.where(Policy.customer_id == customer_id)
        count_stmt = count_stmt.where(Policy.customer_id == customer_id)

    if status is not None:
        stmt = stmt.where(Policy.status == status)
        count_stmt = count_stmt.where(Policy.status == status)
    if policy_type is not None:
        stmt = stmt.where(Policy.policy_type == policy_type)
        count_stmt = count_stmt.where(Policy.policy_type == policy_type)

    total = await db.scalar(count_stmt) or 0
    stmt = stmt.order_by(Policy.created_at.desc()).offset((page - 1) * per_page).limit(
        per_page
    )
    return list((await db.scalars(stmt)).all()), total


async def cancel_policy(
    db: AsyncSession, policy_id: uuid.UUID, reason: str, actor: User
) -> Policy:
    policy = await get_policy(db, policy_id)
    if policy.status not in {PolicyStatus.active, PolicyStatus.lapsed}:
        raise AppError(
            f"Cannot cancel a policy in status '{policy.status}'.",
            code="INVALID_POLICY_STATUS",
            status_code=409,
        )
    old_status = policy.status.value
    policy.status = PolicyStatus.cancelled
    policy.cancellation_reason = reason
    policy.cancelled_at = datetime.now(UTC)
    await audit_service.record(
        db,
        action="policy.status_changed",
        entity_type="policy",
        entity_id=policy.id,
        actor=actor,
        old_value={"status": old_status},
        new_value={"status": PolicyStatus.cancelled.value, "reason": reason},
    )
    notif = await notification_service.notify_customer(
        db,
        policy.customer_id,
        notification_type=NotificationType.general,
        title="Policy cancelled",
        body=f"Policy {policy.policy_number} has been cancelled. Reason: {reason}",
        related_entity_type="policy",
        related_entity_id=policy.id,
    )
    await db.commit()
    await db.refresh(policy)
    if notif:
        notification_service.queue_email(notif.id)
    return policy


async def reinstate_policy(
    db: AsyncSession, policy_id: uuid.UUID, actor: User
) -> Policy:
    """Reinstate a lapsed policy (manager+). Specs: within 30 days of lapse."""
    policy = await get_policy(db, policy_id)
    if policy.status != PolicyStatus.lapsed:
        raise AppError(
            "Only lapsed policies can be reinstated.",
            code="INVALID_POLICY_STATUS",
            status_code=409,
        )
    old_status = policy.status.value
    policy.status = PolicyStatus.active
    policy.cancellation_reason = None
    policy.cancelled_at = None
    await audit_service.record(
        db,
        action="policy.status_changed",
        entity_type="policy",
        entity_id=policy.id,
        actor=actor,
        old_value={"status": old_status},
        new_value={"status": PolicyStatus.active.value, "reason": "reinstated"},
    )
    await db.commit()
    await db.refresh(policy)
    return policy


async def to_read(db: AsyncSession, policy: Policy) -> PolicyRead:
    auto = await db.scalar(
        select(PolicyAutoDetails).where(PolicyAutoDetails.policy_id == policy.id)
    )
    home = await db.scalar(
        select(PolicyHomeDetails).where(PolicyHomeDetails.policy_id == policy.id)
    )
    life = await db.scalar(
        select(PolicyLifeDetails).where(PolicyLifeDetails.policy_id == policy.id)
    )
    bens = list(
        (
            await db.scalars(
                select(Beneficiary).where(Beneficiary.policy_id == policy.id)
            )
        ).all()
    )
    schedules = list(
        (
            await db.scalars(
                select(PremiumSchedule)
                .where(PremiumSchedule.policy_id == policy.id)
                .order_by(PremiumSchedule.due_date)
            )
        ).all()
    )
    paid_totals = await billing.paid_by_schedule(db, policy.id)

    return PolicyRead(
        id=policy.id,
        policy_number=policy.policy_number,
        customer_id=policy.customer_id,
        quote_id=policy.quote_id,
        policy_type=policy.policy_type,
        status=policy.status,
        effective_date=policy.effective_date,
        expiration_date=policy.expiration_date,
        annual_premium=policy.annual_premium,
        payment_frequency=policy.payment_frequency,
        agent_id=policy.agent_id,
        underwriter_id=policy.underwriter_id,
        cancellation_reason=policy.cancellation_reason,
        cancelled_at=policy.cancelled_at,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
        auto_details=(
            {
                "vin": auto.vin,
                "make": auto.make,
                "model": auto.model,
                "year": auto.year,
                "vehicle_type": auto.vehicle_type,
                "primary_use": auto.primary_use,
                "annual_mileage": auto.annual_mileage,
                "garaging_zip": auto.garaging_zip,
                "coverage_type": auto.coverage_type,
                "liability_limit": auto.liability_limit,
                "collision_deductible": auto.collision_deductible,
                "comprehensive_deductible": auto.comprehensive_deductible,
                "uninsured_motorist": auto.uninsured_motorist,
                "roadside_assistance": auto.roadside_assistance,
                "rental_reimbursement": auto.rental_reimbursement,
            }
            if auto
            else None
        ),
        home_details=(
            {
                "property_address_line1": home.property_address_line1,
                "property_address_line2": home.property_address_line2,
                "city": home.city,
                "state": home.state,
                "zip": home.zip,
                "year_built": home.year_built,
                "square_footage": home.square_footage,
                "construction_type": home.construction_type,
                "roof_type": home.roof_type,
                "roof_year": home.roof_year,
                "home_value": home.home_value,
                "dwelling_coverage": home.dwelling_coverage,
                "personal_property_coverage": home.personal_property_coverage,
                "liability_coverage": home.liability_coverage,
                "deductible": home.deductible,
                "flood_coverage": home.flood_coverage,
                "earthquake_coverage": home.earthquake_coverage,
                "home_business_coverage": home.home_business_coverage,
            }
            if home
            else None
        ),
        life_details=(
            {
                "coverage_amount": life.coverage_amount,
                "policy_term_years": life.policy_term_years,
                "life_type": life.life_type,
                "tobacco_user": life.tobacco_user,
                "health_class": life.health_class,
                "premium_mode": life.premium_mode,
            }
            if life
            else None
        ),
        beneficiaries=[
            BeneficiaryRead(
                id=b.id,
                full_name=b.full_name,
                relationship_type=b.relationship_type,
                allocation_pct=b.allocation_pct,
                ssn_last4=b.ssn_last4,
                date_of_birth=b.date_of_birth,
                is_contingent=b.is_contingent,
            )
            for b in bens
        ],
        premium_schedules=[
            _schedule_read(s, paid_totals.get(s.id, Decimal("0.00")))
            for s in schedules
        ],
    )


def _schedule_read(
    schedule: PremiumSchedule, amount_paid: Decimal
) -> PremiumScheduleRead:
    read = PremiumScheduleRead.model_validate(schedule)
    read.amount_paid = amount_paid
    read.balance = billing.outstanding_balance(schedule.amount_due, amount_paid)
    return read


def to_list_item(policy: Policy) -> PolicyListItem:
    return PolicyListItem.model_validate(policy)
