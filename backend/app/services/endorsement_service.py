"""Endorsement (mid-term change) workflow."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, ForbiddenError, NotFoundError
from app.models.enums import (
    EndorsementStatus,
    NotificationType,
    PolicyStatus,
    UserRole,
)
from app.models.policy import Endorsement, Policy
from app.models.user import User
from app.schemas.endorsement import EndorsementCreate, EndorsementRead
from app.services import notification_service

# Specs: manager approval required when premium increase exceeds this amount.
LARGE_ENDORSEMENT_THRESHOLD = Decimal("500")


def to_read(endorsement: Endorsement) -> EndorsementRead:
    return EndorsementRead.model_validate(endorsement)


async def _next_endorsement_number(db: AsyncSession, policy: Policy) -> str:
    count = await db.scalar(
        select(func.count(Endorsement.id)).where(Endorsement.policy_id == policy.id)
    )
    seq = (count or 0) + 1
    return f"END-{policy.policy_number}-{seq:03d}"


async def list_endorsements(
    db: AsyncSession, policy_id: uuid.UUID
) -> list[Endorsement]:
    result = await db.scalars(
        select(Endorsement)
        .where(Endorsement.policy_id == policy_id)
        .order_by(Endorsement.created_at.desc())
    )
    return list(result.all())


async def get_endorsement(
    db: AsyncSession, policy_id: uuid.UUID, endorsement_id: uuid.UUID
) -> Endorsement:
    endorsement = await db.scalar(
        select(Endorsement).where(
            Endorsement.id == endorsement_id,
            Endorsement.policy_id == policy_id,
        )
    )
    if endorsement is None:
        raise NotFoundError("Endorsement not found.", code="ENDORSEMENT_NOT_FOUND")
    return endorsement


async def create_endorsement(
    db: AsyncSession,
    policy_id: uuid.UUID,
    actor: User,
    payload: EndorsementCreate,
) -> Endorsement:
    policy = await db.scalar(select(Policy).where(Policy.id == policy_id))
    if policy is None:
        raise NotFoundError("Policy not found.", code="POLICY_NOT_FOUND")
    if policy.status != PolicyStatus.active:
        raise AppError(
            "Endorsements can only be requested on active policies.",
            code="POLICY_NOT_ACTIVE",
            status_code=409,
        )

    endorsement = Endorsement(
        policy_id=policy.id,
        endorsement_number=await _next_endorsement_number(db, policy),
        type=payload.type,
        effective_date=payload.effective_date,
        description=payload.description,
        premium_impact=payload.premium_impact,
        status=EndorsementStatus.pending,
        requested_by=actor.id,
    )
    db.add(endorsement)
    await db.commit()
    await db.refresh(endorsement)
    return endorsement


async def approve_endorsement(
    db: AsyncSession,
    policy_id: uuid.UUID,
    endorsement_id: uuid.UUID,
    actor: User,
) -> Endorsement:
    endorsement = await get_endorsement(db, policy_id, endorsement_id)
    if endorsement.status != EndorsementStatus.pending:
        raise AppError(
            f"Cannot approve endorsement in status '{endorsement.status}'.",
            code="INVALID_ENDORSEMENT_STATUS",
            status_code=409,
        )

    impact = endorsement.premium_impact or Decimal("0")
    if impact > LARGE_ENDORSEMENT_THRESHOLD and actor.role not in {
        UserRole.manager,
        UserRole.super_admin,
    }:
        raise ForbiddenError(
            f"Endorsements increasing premium by more than "
            f"${LARGE_ENDORSEMENT_THRESHOLD} require manager approval."
        )

    policy = await db.scalar(select(Policy).where(Policy.id == policy_id))
    if policy is None:
        raise NotFoundError("Policy not found.", code="POLICY_NOT_FOUND")
    if policy.status != PolicyStatus.active:
        raise AppError(
            "Cannot approve endorsement on a non-active policy.",
            code="POLICY_NOT_ACTIVE",
            status_code=409,
        )

    new_premium = policy.annual_premium + impact
    if new_premium < Decimal("0"):
        raise AppError(
            "Approval would result in a negative annual premium.",
            code="INVALID_PREMIUM_IMPACT",
            status_code=422,
        )

    policy.annual_premium = new_premium
    endorsement.status = EndorsementStatus.approved
    endorsement.approved_by = actor.id
    notif = await notification_service.notify_customer(
        db,
        policy.customer_id,
        notification_type=NotificationType.endorsement_approved,
        title="Endorsement approved",
        body=(
            f"An endorsement on policy {policy.policy_number} was approved. "
            f"New annual premium: ${new_premium:,.2f}."
        ),
        related_entity_type="endorsement",
        related_entity_id=endorsement.id,
    )
    await db.commit()
    await db.refresh(endorsement)
    if notif:
        notification_service.queue_email(notif.id)
    return endorsement


async def reject_endorsement(
    db: AsyncSession,
    policy_id: uuid.UUID,
    endorsement_id: uuid.UUID,
    actor: User,
    reason: str | None = None,
) -> Endorsement:
    endorsement = await get_endorsement(db, policy_id, endorsement_id)
    if endorsement.status != EndorsementStatus.pending:
        raise AppError(
            f"Cannot reject endorsement in status '{endorsement.status}'.",
            code="INVALID_ENDORSEMENT_STATUS",
            status_code=409,
        )
    endorsement.status = EndorsementStatus.rejected
    endorsement.approved_by = actor.id
    if reason:
        note = endorsement.description or ""
        endorsement.description = f"{note}\n[Rejected] {reason}".strip()
    await db.commit()
    await db.refresh(endorsement)
    return endorsement
