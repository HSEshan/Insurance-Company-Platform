"""Unit tests for premium billing arithmetic and installment status rules."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.models.enums import PaymentMethod, PremiumScheduleStatus
from app.services.billing import (
    SELF_REFERENCING_METHODS,
    build_reference_number,
    outstanding_balance,
    resolve_schedule_status,
)

TODAY = date(2026, 6, 15)
DUE = Decimal("123.35")


def status_for(
    amount_paid: Decimal | str,
    due_date: date,
    current: PremiumScheduleStatus = PremiumScheduleStatus.upcoming,
) -> PremiumScheduleStatus:
    return resolve_schedule_status(
        amount_due=DUE,
        amount_paid=Decimal(amount_paid),
        due_date=due_date,
        today=TODAY,
        current=current,
    )


# --------------------------------------------------------------------------- #
# Installment status
# --------------------------------------------------------------------------- #
def test_future_installment_is_upcoming() -> None:
    assert status_for("0", date(2026, 7, 15)) == PremiumScheduleStatus.upcoming


def test_installment_due_today_is_due() -> None:
    assert status_for("0", TODAY) == PremiumScheduleStatus.due


def test_installment_past_due_is_overdue() -> None:
    assert status_for("0", date(2026, 6, 14)) == PremiumScheduleStatus.overdue


def test_paid_in_full_is_paid_even_when_late() -> None:
    assert status_for(DUE, date(2026, 5, 1)) == PremiumScheduleStatus.paid


def test_overpayment_still_reads_as_paid() -> None:
    assert status_for("500.00", date(2026, 5, 1)) == PremiumScheduleStatus.paid


def test_partial_payment_does_not_settle_the_installment() -> None:
    # A cent short is still short: the installment stays open.
    assert status_for(DUE - Decimal("0.01"), date(2026, 6, 14)) == (
        PremiumScheduleStatus.overdue
    )


def test_partial_payment_on_a_future_installment_stays_upcoming() -> None:
    assert status_for("50.00", date(2026, 7, 15)) == PremiumScheduleStatus.upcoming


def test_waived_installment_is_never_reopened() -> None:
    # A waiver is a deliberate write-off; the calendar must not undo it.
    assert status_for("0", date(2026, 1, 1), PremiumScheduleStatus.waived) == (
        PremiumScheduleStatus.waived
    )


def test_voiding_a_payment_reopens_a_previously_paid_installment() -> None:
    # Reversing the money returns the balance, so the derived status must follow.
    assert status_for(DUE, date(2026, 6, 1)) == PremiumScheduleStatus.paid
    assert status_for("0", date(2026, 6, 1), PremiumScheduleStatus.paid) == (
        PremiumScheduleStatus.overdue
    )


# --------------------------------------------------------------------------- #
# Balances
# --------------------------------------------------------------------------- #
def test_balance_is_the_unpaid_remainder() -> None:
    assert outstanding_balance(DUE, Decimal("23.35")) == Decimal("100.00")


def test_balance_never_goes_negative() -> None:
    assert outstanding_balance(DUE, Decimal("999.00")) == Decimal("0.00")


def test_balance_keeps_cent_precision() -> None:
    balance = outstanding_balance(Decimal("100.00"), Decimal("33.33"))
    assert balance == Decimal("66.67")
    assert balance.as_tuple().exponent == -2


# --------------------------------------------------------------------------- #
# Reference numbers
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("method", "prefix"),
    [
        (PaymentMethod.ach, "ACH"),
        (PaymentMethod.credit_card, "CARD"),
        (PaymentMethod.check, "CHK"),
        (PaymentMethod.wire, "WIRE"),
        (PaymentMethod.cash, "CASH"),
    ],
)
def test_reference_number_is_prefixed_by_method(
    method: PaymentMethod, prefix: str
) -> None:
    reference = build_reference_number(method, on=TODAY, token="AB12CD")
    assert reference == f"{prefix}-20260615-AB12CD"


def test_every_method_can_produce_a_reference() -> None:
    for method in PaymentMethod:
        assert build_reference_number(method)


def test_generated_references_are_unique() -> None:
    references = {build_reference_number(PaymentMethod.ach) for _ in range(200)}
    assert len(references) == 200


def test_paper_instruments_carry_their_own_reference() -> None:
    # Check and wire numbers come off the instrument, so the agent must supply
    # them; the electronic methods are simulated and self-reference.
    assert SELF_REFERENCING_METHODS == {PaymentMethod.check, PaymentMethod.wire}
