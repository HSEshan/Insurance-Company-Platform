"""Unit tests for quote workflow helpers and policy binding utilities.

These tests do not require a database — they cover pure helpers and the
rating-driven hard-decline paths used by the quote service.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.models.enums import PaymentFrequency, PolicyType, RiskTier
from app.services.policy_service import (
    build_policy_number,
    generate_premium_schedule_rows,
)
from app.services.quote_service import LARGE_PREMIUM_THRESHOLD
from app.services.rating import HomeRatingInput, rate_home


def test_policy_number_format() -> None:
    assert build_policy_number(PolicyType.auto, 2026, 123) == "AUTO-2026-000123"
    assert build_policy_number(PolicyType.home, 2026, 1) == "HOME-2026-000001"
    assert build_policy_number(PolicyType.life, 2026, 42) == "LIFE-2026-000042"


def test_monthly_premium_schedule_sums_to_annual() -> None:
    annual = Decimal("1200.00")
    rows = generate_premium_schedule_rows(
        annual_premium=annual,
        payment_frequency=PaymentFrequency.monthly,
        effective_date=date(2026, 1, 15),
    )
    assert len(rows) == 12
    assert sum((amt for _, amt in rows), Decimal("0")) == annual
    assert rows[0][0] == date(2026, 1, 15)
    assert rows[1][0] == date(2026, 2, 15)


def test_quarterly_premium_schedule() -> None:
    annual = Decimal("1000.00")
    rows = generate_premium_schedule_rows(
        annual_premium=annual,
        payment_frequency=PaymentFrequency.quarterly,
        effective_date=date(2026, 3, 1),
    )
    assert len(rows) == 4
    assert sum((amt for _, amt in rows), Decimal("0")) == annual
    assert rows[1][0] == date(2026, 6, 1)


def test_annual_premium_schedule_single_row() -> None:
    annual = Decimal("2500.50")
    rows = generate_premium_schedule_rows(
        annual_premium=annual,
        payment_frequency=PaymentFrequency.annual,
        effective_date=date(2026, 7, 1),
    )
    assert rows == [(date(2026, 7, 1), annual)]


def test_premium_schedule_handles_rounding_remainder() -> None:
    # 100 / 12 does not divide evenly; final installment absorbs remainder.
    annual = Decimal("100.00")
    rows = generate_premium_schedule_rows(
        annual_premium=annual,
        payment_frequency=PaymentFrequency.monthly,
        effective_date=date(2026, 1, 1),
    )
    assert sum((amt for _, amt in rows), Decimal("0")) == annual
    assert rows[0][1] == Decimal("8.33")
    assert rows[-1][1] == Decimal("8.37")


def test_month_clamp_on_short_months() -> None:
    rows = generate_premium_schedule_rows(
        annual_premium=Decimal("1200.00"),
        payment_frequency=PaymentFrequency.monthly,
        effective_date=date(2026, 1, 31),
    )
    assert rows[1][0] == date(2026, 2, 28)


def test_home_flood_zone_without_rider_is_declined() -> None:
    result = rate_home(
        HomeRatingInput(
            state="FL",
            dwelling_coverage=Decimal("300000"),
            year_built=2000,
            roof_year=2015,
            in_flood_zone=True,
            has_flood_rider=False,
        )
    )
    assert result.declined is True
    assert result.risk_tier == RiskTier.declined
    assert result.decline_reasons


def test_home_flood_zone_with_rider_is_accepted() -> None:
    result = rate_home(
        HomeRatingInput(
            state="FL",
            dwelling_coverage=Decimal("300000"),
            year_built=2000,
            roof_year=2015,
            in_flood_zone=True,
            has_flood_rider=True,
        )
    )
    assert result.declined is False
    assert result.risk_tier != RiskTier.declined


def test_large_premium_threshold_is_ten_thousand() -> None:
    assert LARGE_PREMIUM_THRESHOLD == Decimal("10000")


def test_quote_create_requires_matching_lob() -> None:
    from pydantic import ValidationError

    from app.schemas.quote import QuoteCreate

    with pytest.raises(ValidationError):
        QuoteCreate(
            policy_type=PolicyType.auto,
            effective_date=date(2026, 9, 1),
        )
