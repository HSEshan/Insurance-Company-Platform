"""Unit tests for reporting helpers (no database required)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from app.services.report_service import (
    add_months,
    compute_loss_ratio,
    fill_month_counts,
    month_buckets,
    month_end,
    month_start,
    year_month,
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


def test_month_buckets_are_twelve_and_include_current() -> None:
    buckets = month_buckets(date(2026, 8, 20))
    assert len(buckets) == 12
    assert buckets[0] == date(2025, 9, 1)
    assert buckets[-1] == date(2026, 8, 1)


def test_month_buckets_cross_year_from_january() -> None:
    buckets = month_buckets(date(2026, 1, 5), months=12)
    assert buckets[0] == date(2025, 2, 1)
    assert buckets[-1] == date(2026, 1, 1)


def test_fill_month_counts_defaults_missing_months_to_zero() -> None:
    buckets = month_buckets(date(2026, 3, 1), months=3)
    filled = fill_month_counts(buckets, {"2026-01": 2, "2026-03": 5})
    assert [row.month for row in filled] == ["2026-01", "2026-02", "2026-03"]
    assert [row.count for row in filled] == [2, 0, 5]


def test_year_month_accepts_datetime() -> None:
    assert year_month(date(2026, 8, 13)) == "2026-08"
    assert year_month(datetime(2026, 8, 1, 0, 0)) == "2026-08"
