"""Claims lifecycle: submit, assign, investigate, adjudicate, pay, notes."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, ForbiddenError, NotFoundError
from app.models.billing import Payment
from app.models.claim import Claim, ClaimNote
from app.models.customer import Customer
from app.models.enums import (
    ClaimNoteType,
    ClaimStatus,
    ClaimType,
    NotificationType,
    PaymentStatus,
    PaymentType,
    PolicyStatus,
    PolicyType,
    UserRole,
)
from app.models.policy import Policy
from app.models.user import User
from app.schemas.claim import (
    ClaimApprove,
    ClaimCreate,
    ClaimListItem,
    ClaimNoteCreate,
    ClaimNoteRead,
    ClaimRead,
    ClaimReject,
    ClaimResolveDispute,
)
from app.services import audit_service, notification_service

LARGE_CLAIM_THRESHOLD = Decimal("10000")
FRAUD_FLAG_THRESHOLD = Decimal("0.7")

_CLAIM_TYPES_BY_POLICY: dict[PolicyType, set[ClaimType]] = {
    PolicyType.auto: {
        ClaimType.auto_collision,
        ClaimType.auto_comprehensive,
        ClaimType.auto_liability,
    },
    PolicyType.home: {
        ClaimType.home_dwelling,
        ClaimType.home_personal_property,
        ClaimType.home_liability,
    },
    PolicyType.life: {ClaimType.life_death_benefit},
}

_STAFF_VIEWERS = {
    UserRole.agent,
    UserRole.adjuster,
    UserRole.manager,
    UserRole.super_admin,
}


def build_claim_number(year: int, seq: int) -> str:
    return f"CLM-{year}-{seq:06d}"


def score_claim_fraud(
    *,
    policy_effective: date,
    incident_date: date,
    reported_date: date,
    estimated_damage: Decimal | None,
    prior_claims_12mo: int,
) -> tuple[Decimal, bool, list[str]]:
    """Rule-based fraud score in ``[0, 1]``. Returns (score, flag, signals)."""
    signals: list[str] = []
    score = Decimal("0")

    if (reported_date - policy_effective).days <= 30:
        score += Decimal("0.25")
        signals.append("Claim within 30 days of policy inception")
    if prior_claims_12mo > 2:
        score += Decimal("0.25")
        signals.append("More than two claims in the last 12 months")
    if (reported_date - incident_date).days > 14:
        score += Decimal("0.20")
        signals.append("Incident reported more than 14 days after occurrence")
    if estimated_damage is not None and estimated_damage >= Decimal("50000"):
        score += Decimal("0.20")
        signals.append("High estimated damage (≥ $50,000)")

    score = min(score, Decimal("1")).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    return score, score >= FRAUD_FLAG_THRESHOLD, signals


def to_list_item(claim: Claim) -> ClaimListItem:
    return ClaimListItem.model_validate(claim)


def to_read(claim: Claim, notes: list[ClaimNote] | None = None) -> ClaimRead:
    return ClaimRead(
        id=claim.id,
        claim_number=claim.claim_number,
        policy_id=claim.policy_id,
        customer_id=claim.customer_id,
        claim_type=claim.claim_type,
        incident_date=claim.incident_date,
        reported_date=claim.reported_date,
        description=claim.description,
        incident_location=claim.incident_location,
        estimated_damage=claim.estimated_damage,
        approved_amount=claim.approved_amount,
        final_payout=claim.final_payout,
        status=claim.status,
        fraud_flag=claim.fraud_flag,
        fraud_score=claim.fraud_score,
        adjuster_id=claim.adjuster_id,
        created_at=claim.created_at,
        updated_at=claim.updated_at,
        notes=[ClaimNoteRead.model_validate(n) for n in (notes or [])],
    )


async def next_claim_number(db: AsyncSession) -> str:
    result = await db.execute(text("SELECT nextval('claim_number_seq')"))
    seq = int(result.scalar_one())
    return build_claim_number(datetime.now(UTC).year, seq)


async def get_claim(db: AsyncSession, claim_id: uuid.UUID) -> Claim:
    claim = await db.scalar(select(Claim).where(Claim.id == claim_id))
    if claim is None:
        raise NotFoundError("Claim not found.", code="CLAIM_NOT_FOUND")
    return claim


async def assert_claim_access(db: AsyncSession, claim: Claim, actor: User) -> None:
    if actor.role in _STAFF_VIEWERS:
        return
    if actor.role == UserRole.customer:
        customer = await db.scalar(select(Customer).where(Customer.user_id == actor.id))
        if customer is not None and customer.id == claim.customer_id:
            return
    raise ForbiddenError("You do not have access to this claim.")


async def list_claims(
    db: AsyncSession,
    actor: User,
    *,
    page: int,
    per_page: int,
    status: ClaimStatus | None = None,
    claim_type: ClaimType | None = None,
) -> tuple[list[Claim], int]:
    stmt = select(Claim)
    count_stmt = select(func.count(Claim.id))

    if actor.role == UserRole.customer:
        customer = await db.scalar(select(Customer).where(Customer.user_id == actor.id))
        if customer is None:
            return [], 0
        stmt = stmt.where(Claim.customer_id == customer.id)
        count_stmt = count_stmt.where(Claim.customer_id == customer.id)
    elif actor.role == UserRole.adjuster:
        stmt = stmt.where(Claim.adjuster_id == actor.id)
        count_stmt = count_stmt.where(Claim.adjuster_id == actor.id)

    if status is not None:
        stmt = stmt.where(Claim.status == status)
        count_stmt = count_stmt.where(Claim.status == status)
    if claim_type is not None:
        stmt = stmt.where(Claim.claim_type == claim_type)
        count_stmt = count_stmt.where(Claim.claim_type == claim_type)

    total = await db.scalar(count_stmt) or 0
    stmt = stmt.order_by(Claim.created_at.desc()).offset((page - 1) * per_page).limit(
        per_page
    )
    return list((await db.scalars(stmt)).all()), total


async def _prior_claims_count(
    db: AsyncSession, customer_id: uuid.UUID, since: date
) -> int:
    count = await db.scalar(
        select(func.count(Claim.id)).where(
            Claim.customer_id == customer_id,
            Claim.incident_date >= since,
        )
    )
    return int(count or 0)


async def submit_claim(db: AsyncSession, actor: User, payload: ClaimCreate) -> Claim:
    policy = await db.scalar(select(Policy).where(Policy.id == payload.policy_id))
    if policy is None:
        raise NotFoundError("Policy not found.", code="POLICY_NOT_FOUND")
    if policy.status != PolicyStatus.active:
        raise AppError(
            "Claims can only be filed against active policies.",
            code="POLICY_NOT_ACTIVE",
            status_code=409,
        )

    if actor.role == UserRole.customer:
        customer = await db.scalar(select(Customer).where(Customer.user_id == actor.id))
        if customer is None or customer.id != policy.customer_id:
            raise ForbiddenError("You can only file claims on your own policies.")
    elif actor.role not in {UserRole.super_admin, UserRole.agent}:
        raise ForbiddenError("You cannot submit claims.")

    allowed = _CLAIM_TYPES_BY_POLICY[policy.policy_type]
    if payload.claim_type not in allowed:
        raise AppError(
            f"Claim type '{payload.claim_type}' is not valid for a "
            f"{policy.policy_type} policy.",
            code="INVALID_CLAIM_TYPE",
            status_code=422,
        )

    if payload.incident_date > date.today():
        raise AppError(
            "Incident date cannot be in the future.",
            code="INVALID_INCIDENT_DATE",
            status_code=422,
        )
    if payload.incident_date < policy.effective_date:
        raise AppError(
            "Incident date is before the policy effective date.",
            code="INCIDENT_BEFORE_COVERAGE",
            status_code=422,
        )

    reported = date.today()
    prior = await _prior_claims_count(
        db, policy.customer_id, reported - timedelta(days=365)
    )
    score, flagged, signals = score_claim_fraud(
        policy_effective=policy.effective_date,
        incident_date=payload.incident_date,
        reported_date=reported,
        estimated_damage=payload.estimated_damage,
        prior_claims_12mo=prior,
    )

    claim = Claim(
        claim_number=await next_claim_number(db),
        policy_id=policy.id,
        customer_id=policy.customer_id,
        claim_type=payload.claim_type,
        incident_date=payload.incident_date,
        reported_date=reported,
        description=payload.description,
        incident_location=payload.incident_location,
        estimated_damage=payload.estimated_damage,
        status=ClaimStatus.submitted,
        fraud_flag=flagged,
        fraud_score=score,
    )
    db.add(claim)
    await db.flush()

    if signals:
        db.add(
            ClaimNote(
                claim_id=claim.id,
                author_id=None,
                note_type=ClaimNoteType.system,
                body="Fraud scoring signals: " + "; ".join(signals),
                is_visible_to_customer=False,
            )
        )

    notif = await notification_service.notify_customer(
        db,
        claim.customer_id,
        notification_type=NotificationType.claim_submitted,
        title="Claim submitted",
        body=(
            f"We received claim {claim.claim_number}. An adjuster will review "
            f"it shortly."
        ),
        related_entity_type="claim",
        related_entity_id=claim.id,
    )
    await db.commit()
    await db.refresh(claim)
    if notif:
        notification_service.queue_email(notif.id)
    return claim


async def assign_claim(
    db: AsyncSession, claim_id: uuid.UUID, adjuster_id: uuid.UUID
) -> Claim:
    claim = await get_claim(db, claim_id)
    if claim.status not in {ClaimStatus.submitted, ClaimStatus.assigned}:
        raise AppError(
            f"Cannot assign claim in status '{claim.status}'.",
            code="INVALID_CLAIM_STATUS",
            status_code=409,
        )
    adjuster = await db.scalar(select(User).where(User.id == adjuster_id))
    if adjuster is None or adjuster.role != UserRole.adjuster:
        raise AppError(
            "adjuster_id must reference an active adjuster user.",
            code="INVALID_ADJUSTER",
            status_code=422,
        )
    if not adjuster.is_active:
        raise AppError(
            "Adjuster account is inactive.",
            code="INVALID_ADJUSTER",
            status_code=422,
        )

    claim.adjuster_id = adjuster_id
    claim.status = ClaimStatus.assigned
    adjuster_notif = await notification_service.emit(
        db,
        user_id=adjuster_id,
        notification_type=NotificationType.claim_status_changed,
        title="Claim assigned to you",
        body=f"Claim {claim.claim_number} has been assigned for your review.",
        related_entity_type="claim",
        related_entity_id=claim.id,
    )
    await db.commit()
    await db.refresh(claim)
    notification_service.queue_email(adjuster_notif.id)
    return claim


async def start_investigation(db: AsyncSession, claim_id: uuid.UUID, actor: User) -> Claim:
    claim = await get_claim(db, claim_id)
    if claim.status not in {
        ClaimStatus.assigned,
        ClaimStatus.info_requested,
    }:
        raise AppError(
            f"Cannot investigate claim in status '{claim.status}'.",
            code="INVALID_CLAIM_STATUS",
            status_code=409,
        )
    _assert_adjuster_or_manager(claim, actor)
    claim.status = ClaimStatus.investigating
    await db.commit()
    await db.refresh(claim)
    return claim


def _assert_adjuster_or_manager(claim: Claim, actor: User) -> None:
    if actor.role in {UserRole.manager, UserRole.super_admin}:
        return
    if actor.role == UserRole.adjuster and claim.adjuster_id == actor.id:
        return
    raise ForbiddenError("Only the assigned adjuster or a manager can perform this action.")


async def request_info(
    db: AsyncSession, claim_id: uuid.UUID, actor: User, message: str
) -> Claim:
    claim = await get_claim(db, claim_id)
    if claim.status not in {ClaimStatus.investigating, ClaimStatus.assigned}:
        raise AppError(
            f"Cannot request info for claim in status '{claim.status}'.",
            code="INVALID_CLAIM_STATUS",
            status_code=409,
        )
    _assert_adjuster_or_manager(claim, actor)
    claim.status = ClaimStatus.info_requested
    db.add(
        ClaimNote(
            claim_id=claim.id,
            author_id=actor.id,
            note_type=ClaimNoteType.customer_facing,
            body=message,
            is_visible_to_customer=True,
        )
    )
    notif = await notification_service.notify_customer(
        db,
        claim.customer_id,
        notification_type=NotificationType.claim_status_changed,
        title="More information needed",
        body=f"Regarding claim {claim.claim_number}: {message}",
        related_entity_type="claim",
        related_entity_id=claim.id,
    )
    await db.commit()
    await db.refresh(claim)
    if notif:
        notification_service.queue_email(notif.id)
    return claim


async def approve_claim(
    db: AsyncSession, claim_id: uuid.UUID, actor: User, payload: ClaimApprove
) -> Claim:
    claim = await get_claim(db, claim_id)
    if claim.status not in {
        ClaimStatus.investigating,
        ClaimStatus.info_requested,
        ClaimStatus.assigned,
    }:
        raise AppError(
            f"Cannot approve claim in status '{claim.status}'.",
            code="INVALID_CLAIM_STATUS",
            status_code=409,
        )
    _assert_adjuster_or_manager(claim, actor)

    if payload.approved_amount > LARGE_CLAIM_THRESHOLD and actor.role not in {
        UserRole.manager,
        UserRole.super_admin,
    }:
        raise ForbiddenError(
            f"Claims over ${LARGE_CLAIM_THRESHOLD} require manager approval."
        )

    old_status = claim.status.value
    claim.approved_amount = payload.approved_amount
    claim.status = ClaimStatus.approved
    await audit_service.record(
        db,
        action="claim.approved",
        entity_type="claim",
        entity_id=claim.id,
        actor=actor,
        old_value={"status": old_status},
        new_value={
            "status": ClaimStatus.approved.value,
            "approved_amount": str(payload.approved_amount),
        },
    )
    notif = await notification_service.notify_customer(
        db,
        claim.customer_id,
        notification_type=NotificationType.claim_approved,
        title="Claim approved",
        body=(
            f"Claim {claim.claim_number} has been approved for "
            f"${payload.approved_amount:,.2f}."
        ),
        related_entity_type="claim",
        related_entity_id=claim.id,
    )
    await db.commit()
    await db.refresh(claim)
    if notif:
        notification_service.queue_email(notif.id)
    return claim


async def reject_claim(
    db: AsyncSession, claim_id: uuid.UUID, actor: User, payload: ClaimReject
) -> Claim:
    claim = await get_claim(db, claim_id)
    if claim.status not in {
        ClaimStatus.investigating,
        ClaimStatus.info_requested,
        ClaimStatus.assigned,
    }:
        raise AppError(
            f"Cannot reject claim in status '{claim.status}'.",
            code="INVALID_CLAIM_STATUS",
            status_code=409,
        )
    _assert_adjuster_or_manager(claim, actor)
    old_status = claim.status.value
    claim.status = ClaimStatus.rejected
    db.add(
        ClaimNote(
            claim_id=claim.id,
            author_id=actor.id,
            note_type=ClaimNoteType.customer_facing,
            body=f"Claim rejected: {payload.reason}",
            is_visible_to_customer=True,
        )
    )
    await audit_service.record(
        db,
        action="claim.rejected",
        entity_type="claim",
        entity_id=claim.id,
        actor=actor,
        old_value={"status": old_status},
        new_value={"status": ClaimStatus.rejected.value, "reason": payload.reason},
    )
    notif = await notification_service.notify_customer(
        db,
        claim.customer_id,
        notification_type=NotificationType.claim_rejected,
        title="Claim decision",
        body=(
            f"Claim {claim.claim_number} was not approved. Reason: {payload.reason}"
        ),
        related_entity_type="claim",
        related_entity_id=claim.id,
    )
    await db.commit()
    await db.refresh(claim)
    if notif:
        notification_service.queue_email(notif.id)
    return claim


async def dispute_claim(
    db: AsyncSession, claim_id: uuid.UUID, actor: User, reason: str
) -> Claim:
    claim = await get_claim(db, claim_id)
    await assert_claim_access(db, claim, actor)
    if actor.role != UserRole.customer and actor.role != UserRole.super_admin:
        raise ForbiddenError("Only the customer can dispute a rejection.")
    if claim.status != ClaimStatus.rejected:
        raise AppError(
            "Only rejected claims can be disputed.",
            code="INVALID_CLAIM_STATUS",
            status_code=409,
        )
    claim.status = ClaimStatus.disputed
    db.add(
        ClaimNote(
            claim_id=claim.id,
            author_id=actor.id,
            note_type=ClaimNoteType.customer_facing,
            body=f"Customer dispute: {reason}",
            is_visible_to_customer=True,
        )
    )
    pending_email: uuid.UUID | None = None
    if claim.adjuster_id:
        adj_notif = await notification_service.emit(
            db,
            user_id=claim.adjuster_id,
            notification_type=NotificationType.claim_status_changed,
            title="Claim disputed",
            body=f"The customer disputed the decision on {claim.claim_number}.",
            related_entity_type="claim",
            related_entity_id=claim.id,
        )
        pending_email = adj_notif.id
    await db.commit()
    await db.refresh(claim)
    if pending_email:
        notification_service.queue_email(pending_email)
    return claim


async def resolve_dispute(
    db: AsyncSession,
    claim_id: uuid.UUID,
    actor: User,
    payload: ClaimResolveDispute,
) -> Claim:
    claim = await get_claim(db, claim_id)
    if claim.status != ClaimStatus.disputed:
        raise AppError(
            "Claim is not in disputed status.",
            code="INVALID_CLAIM_STATUS",
            status_code=409,
        )
    if payload.uphold_rejection:
        claim.status = ClaimStatus.rejected
        body = "Manager upheld the rejection."
    else:
        if payload.approved_amount is None:
            raise AppError(
                "approved_amount is required when overturning a rejection.",
                code="AMOUNT_REQUIRED",
                status_code=422,
            )
        claim.approved_amount = payload.approved_amount
        claim.status = ClaimStatus.approved
        body = (
            f"Manager overturned rejection; approved amount "
            f"${payload.approved_amount}."
        )
    db.add(
        ClaimNote(
            claim_id=claim.id,
            author_id=actor.id,
            note_type=ClaimNoteType.system,
            body=body,
            is_visible_to_customer=True,
        )
    )
    notif_type = (
        NotificationType.claim_rejected
        if payload.uphold_rejection
        else NotificationType.claim_approved
    )
    notif = await notification_service.notify_customer(
        db,
        claim.customer_id,
        notification_type=notif_type,
        title="Dispute resolved",
        body=f"Claim {claim.claim_number}: {body}",
        related_entity_type="claim",
        related_entity_id=claim.id,
    )
    await db.commit()
    await db.refresh(claim)
    if notif:
        notification_service.queue_email(notif.id)
    return claim


async def pay_claim(db: AsyncSession, claim_id: uuid.UUID, actor: User) -> Claim:
    claim = await get_claim(db, claim_id)
    if claim.status != ClaimStatus.approved:
        raise AppError(
            "Only approved claims can be paid.",
            code="INVALID_CLAIM_STATUS",
            status_code=409,
        )
    if claim.approved_amount is None:
        raise AppError("Claim has no approved amount.", code="AMOUNT_REQUIRED")

    claim.final_payout = claim.approved_amount
    claim.status = ClaimStatus.paid
    db.add(
        Payment(
            claim_id=claim.id,
            customer_id=claim.customer_id,
            payment_type=PaymentType.claim_payout,
            amount=claim.approved_amount,
            status=PaymentStatus.completed,
            processed_at=datetime.now(UTC),
            notes=f"Payout for {claim.claim_number}",
            created_by=actor.id,
            reference_number=f"PAY-{claim.claim_number}",
        )
    )
    db.add(
        ClaimNote(
            claim_id=claim.id,
            author_id=actor.id,
            note_type=ClaimNoteType.system,
            body=f"Payout of ${claim.approved_amount} recorded.",
            is_visible_to_customer=True,
        )
    )
    notif = await notification_service.notify_customer(
        db,
        claim.customer_id,
        notification_type=NotificationType.claim_status_changed,
        title="Claim payout issued",
        body=(
            f"A payout of ${claim.approved_amount:,.2f} has been recorded for "
            f"claim {claim.claim_number}."
        ),
        related_entity_type="claim",
        related_entity_id=claim.id,
    )
    await db.commit()
    await db.refresh(claim)
    if notif:
        notification_service.queue_email(notif.id)
    return claim


async def close_claim(db: AsyncSession, claim_id: uuid.UUID) -> Claim:
    claim = await get_claim(db, claim_id)
    if claim.status not in {ClaimStatus.paid, ClaimStatus.rejected}:
        raise AppError(
            "Only paid or finally rejected claims can be closed.",
            code="INVALID_CLAIM_STATUS",
            status_code=409,
        )
    claim.status = ClaimStatus.closed
    await db.commit()
    await db.refresh(claim)
    return claim


async def list_notes(
    db: AsyncSession, claim: Claim, actor: User
) -> list[ClaimNote]:
    stmt = select(ClaimNote).where(ClaimNote.claim_id == claim.id)
    if actor.role == UserRole.customer:
        stmt = stmt.where(ClaimNote.is_visible_to_customer.is_(True))
    stmt = stmt.order_by(ClaimNote.created_at.asc())
    return list((await db.scalars(stmt)).all())


async def add_note(
    db: AsyncSession, claim_id: uuid.UUID, actor: User, payload: ClaimNoteCreate
) -> ClaimNote:
    claim = await get_claim(db, claim_id)
    _assert_adjuster_or_manager(claim, actor)
    visible = payload.is_visible_to_customer or payload.note_type in {
        ClaimNoteType.customer_facing,
    }
    note = ClaimNote(
        claim_id=claim.id,
        author_id=actor.id,
        note_type=payload.note_type,
        body=payload.body,
        is_visible_to_customer=visible,
    )
    db.add(note)
    if (
        claim.status == ClaimStatus.assigned
        and payload.note_type == ClaimNoteType.investigation
    ):
        claim.status = ClaimStatus.investigating
    await db.commit()
    await db.refresh(note)
    return note
