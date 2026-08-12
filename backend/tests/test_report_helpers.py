"""Unit tests for reporting helpers (no database required)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.report_service import (
    add_months,
    compute_loss_ratio,
    month_end,
    month_start,
)


def test_month_boundaries() -> None:
    assert month_start(date(2026, 8, 10)) == date(2026, 8, 1)
    assert month_end(date(2026, 2, 10)) == date(2026, 2, 28)
    assert month_end(date(2024, 2, 10)) == date(2024, 2, 29)


def test_add_months_clamps_day() -> None:
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 3, 15), -1) == date(2026, 2, 15)


def test_compute_loss_ratio() -> None:
    assert compute_loss_ratio(Decimal("1000.00"), Decimal("250.00")) == Decimal(
        "0.2500"
    )
    assert compute_loss_ratio(Decimal("0"), Decimal("100")) is None
