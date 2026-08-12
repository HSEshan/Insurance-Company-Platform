"""Shared billing arithmetic and read-side aggregates.

Sits below both ``policy_service`` (which reports installment balances) and
``payment_service`` (which posts money against them), so neither has to import
the other. The rules here are deliberately pure or read-only — nothing in this
module mutates state.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import Payment, PremiumSchedule
from app.models.enums import PaymentMethod, PaymentStatus, PremiumScheduleStatus

ZERO = Decimal("0.00")

_REFERENCE_PREFIX: dict[PaymentMethod, str] = {
    PaymentMethod.ach: "ACH",
    PaymentMethod.credit_card: "CARD",
    PaymentMethod.check: "CHK",
    PaymentMethod.wire: "WIRE",
    PaymentMethod.cash: "CASH",
}

# Electronic methods are simulated end to end, so the system issues the
# reference. Paper instruments already carry a number the agent transcribes.
SELF_REFERENCING_METHODS: frozenset[PaymentMethod] = frozenset(
    {PaymentMethod.check, PaymentMethod.wire}
)


def build_reference_number(
    method: PaymentMethod, *, on: date | None = None, token: str | None = None
) -> str:
    """Generate a settlement reference for a simulated electronic payment.

    Card payments are tokenized by design: this reference is all that is kept,
    and no card number ever reaches the database (specs §6.7).
    """
    stamp = (on or date.today()).strftime("%Y%m%d")
    suffix = token or uuid.uuid4().hex[:6].upper()
    return f"{_REFERENCE_PREFIX[method]}-{stamp}-{suffix}"


def resolve_schedule_status(
    *,
    amount_due: Decimal,
    amount_paid: Decimal,
    due_date: date,
    today: date,
    current: PremiumScheduleStatus,
) -> PremiumScheduleStatus:
    """Derive an installment's status from what has been paid against it.

    Status is never set by hand, so the ledger and the schedule cannot drift
    apart and voiding a payment automatically re-opens the installment. A waived
    installment is a deliberate write-off and stays waived.
    """
    if current == PremiumScheduleStatus.waived:
        return PremiumScheduleStatus.waived
    if amount_paid >= amount_due:
        return PremiumScheduleStatus.paid
    if due_date < today:
        return PremiumScheduleStatus.overdue
    if due_date == today:
        return PremiumScheduleStatus.due
    return PremiumScheduleStatus.upcoming


def outstanding_balance(amount_due: Decimal, amount_paid: Decimal) -> Decimal:
    """Never negative: overpayment is refused before it can be recorded."""
    return max(amount_due - amount_paid, ZERO)


async def paid_to_date(db: AsyncSession, schedule_id: uuid.UUID) -> Decimal:
    """Total of completed payments against one installment."""
    total = await db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.schedule_id == schedule_id,
            Payment.status == PaymentStatus.completed,
        )
    )
    return Decimal(total or 0)


async def paid_by_schedule(
    db: AsyncSession, policy_id: uuid.UUID
) -> dict[uuid.UUID, Decimal]:
    """Completed payment totals for every installment on a policy, in one query."""
    rows = await db.execute(
        select(Payment.schedule_id, func.sum(Payment.amount))
        .join(PremiumSchedule, PremiumSchedule.id == Payment.schedule_id)
        .where(
            PremiumSchedule.policy_id == policy_id,
            Payment.status == PaymentStatus.completed,
        )
        .group_by(Payment.schedule_id)
    )
    return {
        schedule_id: Decimal(total) for schedule_id, total in rows if schedule_id
    }
