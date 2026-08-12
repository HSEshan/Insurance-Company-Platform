"""Premium billing commands: recording payments and voiding them.

The arithmetic and the status rules live in ``services/billing.py``; this module
owns authorization, validation, and persistence.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, ForbiddenError, NotFoundError
from app.models.billing import Payment, PremiumSchedule
from app.models.claim import Claim
from app.models.customer import Customer
from app.models.enums import (
    NotificationType,
    PaymentStatus,
    PaymentType,
    PremiumScheduleStatus,
    UserRole,
)
from app.models.policy import Policy
from app.models.user import User
from app.schemas.payment import PaymentCreate, PaymentRead
from app.services import audit_service, billing, notification_service, policy_service

# Adjusters work claims, not billing — the permission matrix in specs §4 gives
# them no visibility into payments at all.
_PAYMENT_VIEWERS: frozenset[UserRole] = frozenset(
    {UserRole.customer, UserRole.agent, UserRole.manager, UserRole.super_admin}
)
_RECORDERS: frozenset[UserRole] = frozenset(
    {UserRole.agent, UserRole.manager, UserRole.super_admin}
)
_VOIDERS: frozenset[UserRole] = frozenset({UserRole.manager, UserRole.super_admin})

_STAFF: frozenset[UserRole] = frozenset(
    {UserRole.agent, UserRole.manager, UserRole.super_admin}
)


async def get_schedule(db: AsyncSession, schedule_id: uuid.UUID) -> PremiumSchedule:
    schedule = await db.scalar(
        select(PremiumSchedule).where(PremiumSchedule.id == schedule_id)
    )
    if schedule is None:
        raise NotFoundError("Installment not found.", code="SCHEDULE_NOT_FOUND")
    return schedule


async def get_payment(db: AsyncSession, payment_id: uuid.UUID) -> Payment:
    payment = await db.scalar(select(Payment).where(Payment.id == payment_id))
    if payment is None:
        raise NotFoundError("Payment not found.", code="PAYMENT_NOT_FOUND")
    return payment


# --------------------------------------------------------------------------- #
# Access control
# --------------------------------------------------------------------------- #
async def assert_can_view_payments(db: AsyncSession, actor: User) -> None:
    if actor.role not in _PAYMENT_VIEWERS:
        raise ForbiddenError("You do not have access to payment records.")


async def _customer_id_for(db: AsyncSession, actor: User) -> uuid.UUID | None:
    customer = await db.scalar(select(Customer).where(Customer.user_id == actor.id))
    return customer.id if customer else None


async def assert_payment_access(db: AsyncSession, payment: Payment, actor: User) -> None:
    await assert_can_view_payments(db, actor)
    if actor.role in _STAFF:
        return
    if payment.customer_id != await _customer_id_for(db, actor):
        raise ForbiddenError("You do not have access to this payment.")


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
async def record_premium_payment(
    db: AsyncSession, actor: User, payload: PaymentCreate
) -> Payment:
    if actor.role not in _RECORDERS:
        raise ForbiddenError("Only an agent or manager can record payments.")

    schedule = await get_schedule(db, payload.schedule_id)
    policy = await policy_service.get_policy(db, schedule.policy_id)
    await policy_service.assert_policy_access(db, policy, actor)

    if schedule.status == PremiumScheduleStatus.waived:
        raise AppError(
            "This installment has been waived and cannot take a payment.",
            code="INSTALLMENT_WAIVED",
            status_code=409,
        )

    already_paid = await billing.paid_to_date(db, schedule.id)
    balance = billing.outstanding_balance(schedule.amount_due, already_paid)
    if balance <= billing.ZERO:
        raise AppError(
            "This installment is already paid in full.",
            code="INSTALLMENT_ALREADY_PAID",
            status_code=409,
        )
    # There is no credit-balance model here, so money with nowhere to go is
    # refused rather than silently absorbed.
    if payload.amount > balance:
        raise AppError(
            f"Payment exceeds the outstanding balance of ${balance:,.2f} "
            f"on this installment.",
            code="PAYMENT_EXCEEDS_BALANCE",
            status_code=422,
        )

    if payload.method in billing.SELF_REFERENCING_METHODS and not payload.reference_number:
        raise AppError(
            f"A reference number is required for {payload.method.value} payments.",
            code="REFERENCE_REQUIRED",
            status_code=422,
        )

    payment = Payment(
        schedule_id=schedule.id,
        customer_id=policy.customer_id,
        payment_type=PaymentType.premium,
        amount=payload.amount,
        method=payload.method,
        status=PaymentStatus.completed,
        reference_number=payload.reference_number
        or billing.build_reference_number(payload.method),
        processed_at=datetime.now(UTC),
        notes=payload.notes,
        created_by=actor.id,
    )
    db.add(payment)
    await db.flush()
    await audit_service.record(
        db,
        action="payment.recorded",
        entity_type="payment",
        entity_id=payment.id,
        actor=actor,
        new_value={
            "amount": str(payload.amount),
            "method": payload.method.value,
            "schedule_id": str(schedule.id),
            "policy_id": str(policy.id),
        },
    )

    await _refresh_schedule_status(db, schedule)
    notif = await notification_service.notify_customer(
        db,
        policy.customer_id,
        notification_type=NotificationType.payment_received,
        title="Payment received",
        body=(
            f"We recorded a {payload.method.value.replace('_', ' ')} payment of "
            f"${payload.amount:,.2f} for policy {policy.policy_number}."
        ),
        related_entity_type="payment",
        related_entity_id=payment.id,
    )
    await db.commit()
    await db.refresh(payment)
    if notif:
        notification_service.queue_email(notif.id)
    return payment


async def void_payment(
    db: AsyncSession, payment_id: uuid.UUID, actor: User, reason: str
) -> Payment:
    if actor.role not in _VOIDERS:
        raise ForbiddenError("Only a manager can void a payment.")

    payment = await get_payment(db, payment_id)
    if payment.status == PaymentStatus.voided:
        raise AppError(
            "This payment has already been voided.",
            code="PAYMENT_ALREADY_VOIDED",
            status_code=409,
        )

    old_status = payment.status.value
    payment.status = PaymentStatus.voided
    stamp = datetime.now(UTC).date().isoformat()
    payment.notes = f"{payment.notes + ' | ' if payment.notes else ''}Voided {stamp}: {reason}"

    # Reversing the money must reopen the installment it settled, otherwise the
    # policy would look current on a balance that is owed again.
    if payment.schedule_id:
        schedule = await get_schedule(db, payment.schedule_id)
        await db.flush()
        await _refresh_schedule_status(db, schedule)

    await audit_service.record(
        db,
        action="payment.voided",
        entity_type="payment",
        entity_id=payment.id,
        actor=actor,
        old_value={"status": old_status},
        new_value={"status": PaymentStatus.voided.value, "reason": reason},
    )
    await db.commit()
    await db.refresh(payment)
    return payment


async def _refresh_schedule_status(
    db: AsyncSession, schedule: PremiumSchedule
) -> None:
    schedule.status = billing.resolve_schedule_status(
        amount_due=schedule.amount_due,
        amount_paid=await billing.paid_to_date(db, schedule.id),
        due_date=schedule.due_date,
        today=date.today(),
        current=schedule.status,
    )


# --------------------------------------------------------------------------- #
# Listing
# --------------------------------------------------------------------------- #
def _payment_query() -> Select:
    """Payments with the context a list view needs, in a single round trip."""
    return (
        select(
            Payment,
            Policy.policy_number,
            Claim.claim_number,
            User.first_name,
            User.last_name,
        )
        .outerjoin(PremiumSchedule, PremiumSchedule.id == Payment.schedule_id)
        .outerjoin(Policy, Policy.id == PremiumSchedule.policy_id)
        .outerjoin(Claim, Claim.id == Payment.claim_id)
        .outerjoin(Customer, Customer.id == Payment.customer_id)
        .outerjoin(User, User.id == Customer.user_id)
    )


def _to_read(row) -> PaymentRead:
    payment, policy_number, claim_number, first_name, last_name = row
    read = PaymentRead.model_validate(payment)
    read.policy_number = policy_number
    read.claim_number = claim_number
    read.customer_name = (
        f"{first_name} {last_name}".strip() if first_name or last_name else None
    )
    return read


async def list_payments(
    db: AsyncSession,
    actor: User,
    *,
    policy_id: uuid.UUID | None = None,
    payment_type: PaymentType | None = None,
    status: PaymentStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[PaymentRead], int]:
    await assert_can_view_payments(db, actor)

    stmt = _payment_query()
    count_stmt = (
        select(func.count(Payment.id))
        .outerjoin(PremiumSchedule, PremiumSchedule.id == Payment.schedule_id)
        .outerjoin(Policy, Policy.id == PremiumSchedule.policy_id)
    )

    if actor.role == UserRole.customer:
        # Scope to the caller's own ledger rather than filtering in the UI.
        customer_id = await _customer_id_for(db, actor)
        if customer_id is None:
            return [], 0
        stmt = stmt.where(Payment.customer_id == customer_id)
        count_stmt = count_stmt.where(Payment.customer_id == customer_id)

    if policy_id is not None:
        stmt = stmt.where(PremiumSchedule.policy_id == policy_id)
        count_stmt = count_stmt.where(PremiumSchedule.policy_id == policy_id)
    if payment_type is not None:
        stmt = stmt.where(Payment.payment_type == payment_type)
        count_stmt = count_stmt.where(Payment.payment_type == payment_type)
    if status is not None:
        stmt = stmt.where(Payment.status == status)
        count_stmt = count_stmt.where(Payment.status == status)

    total = int(await db.scalar(count_stmt) or 0)
    rows = await db.execute(
        stmt.order_by(Payment.created_at.desc()).limit(limit).offset(offset)
    )
    return [_to_read(row) for row in rows], total


async def get_payment_read(
    db: AsyncSession, payment_id: uuid.UUID, actor: User
) -> PaymentRead:
    payment = await get_payment(db, payment_id)
    await assert_payment_access(db, payment, actor)
    row = (await db.execute(_payment_query().where(Payment.id == payment_id))).first()
    if row is None:
        raise NotFoundError("Payment not found.", code="PAYMENT_NOT_FOUND")
    return _to_read(row)
