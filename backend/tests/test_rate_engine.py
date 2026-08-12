"""Unit tests for the Phase 2 rating engine (no database required)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.enums import (
    AutoCoverageType,
    HealthClass,
    LifeType,
    PolicyType,
    RiskTier,
    VehicleType,
)
from app.services.rating import (
    AutoRatingInput,
    HomeRatingInput,
    LifeRatingInput,
    rate_auto,
    rate_home,
    rate_life,
    rate_quote,
)


# --------------------------------------------------------------------------- #
# Auto                                                                         #
# --------------------------------------------------------------------------- #
def _clean_auto(**overrides) -> AutoRatingInput:
    base = dict(
        state="OH",
        driver_age=40,
        vehicle_type=VehicleType.sedan,
        vehicle_year=2018,
        coverage_type=AutoCoverageType.full_coverage,
        annual_mileage=12000,
        collision_deductible=Decimal("500"),
        credit_score=700,
    )
    base.update(overrides)
    return AutoRatingInput(**base)


def test_auto_clean_driver_is_reasonably_priced() -> None:
    result = rate_auto(_clean_auto())
    assert result.annual_premium > 0
    assert result.monthly_premium == (
        result.annual_premium / Decimal(12)
    ).quantize(Decimal("0.01"))
    assert result.risk_tier in {RiskTier.preferred, RiskTier.standard}
    assert result.declined is False


def test_auto_young_driver_pays_more_than_middle_aged() -> None:
    young = rate_auto(_clean_auto(driver_age=18))
    middle = rate_auto(_clean_auto(driver_age=40))
    assert young.annual_premium > middle.annual_premium


def test_auto_violations_increase_premium() -> None:
    clean = rate_auto(_clean_auto())
    risky = rate_auto(_clean_auto(speeding_violations=2, at_fault_claims_3yr=1))
    assert risky.annual_premium > clean.annual_premium


def test_auto_liability_only_cheaper_than_full() -> None:
    liability = rate_auto(_clean_auto(coverage_type=AutoCoverageType.liability_only))
    full = rate_auto(_clean_auto(coverage_type=AutoCoverageType.full_coverage))
    assert liability.annual_premium < full.annual_premium


def test_auto_multi_policy_discount_applies() -> None:
    without = rate_auto(_clean_auto())
    with_home = rate_auto(_clean_auto(has_existing_home_policy=True))
    assert with_home.annual_premium < without.annual_premium
    assert any(f.name == "multi_policy_discount" for f in with_home.factors)


def test_auto_hard_decline_for_dui_and_claims() -> None:
    result = rate_auto(_clean_auto(dui_count=1, at_fault_claims_3yr=3))
    assert result.declined is True
    assert result.risk_tier == RiskTier.declined
    assert result.decline_reasons


def test_auto_higher_deductible_lowers_premium() -> None:
    low = rate_auto(_clean_auto(collision_deductible=Decimal("250")))
    high = rate_auto(_clean_auto(collision_deductible=Decimal("2000")))
    assert high.annual_premium < low.annual_premium


# --------------------------------------------------------------------------- #
# Home                                                                         #
# --------------------------------------------------------------------------- #
def _clean_home(**overrides) -> HomeRatingInput:
    base = dict(
        state="OH",
        dwelling_coverage=Decimal("300000"),
        year_built=2010,
        roof_year=2015,
        deductible=Decimal("1000"),
        credit_score=700,
    )
    base.update(overrides)
    return HomeRatingInput(**base)


def test_home_scales_with_dwelling_coverage() -> None:
    small = rate_home(_clean_home(dwelling_coverage=Decimal("200000")))
    large = rate_home(_clean_home(dwelling_coverage=Decimal("600000")))
    assert large.annual_premium > small.annual_premium


def test_home_flood_zone_adds_surcharge() -> None:
    dry = rate_home(_clean_home())
    flood = rate_home(_clean_home(in_flood_zone=True, has_flood_rider=True))
    assert flood.annual_premium > dry.annual_premium
    assert any(f.name == "flood_surcharge" for f in flood.factors)


def test_home_old_roof_costs_more() -> None:
    new_roof = rate_home(_clean_home(roof_year=2015))
    old_roof = rate_home(_clean_home(roof_year=1995))
    assert old_roof.annual_premium > new_roof.annual_premium


def test_home_security_system_discount() -> None:
    without = rate_home(_clean_home())
    secured = rate_home(_clean_home(has_security_system=True))
    assert secured.annual_premium < without.annual_premium


# --------------------------------------------------------------------------- #
# Life                                                                         #
# --------------------------------------------------------------------------- #
def _clean_life(**overrides) -> LifeRatingInput:
    base = dict(
        age=35,
        coverage_amount=Decimal("500000"),
        life_type=LifeType.term,
        term_years=20,
        health_class=HealthClass.standard,
    )
    base.update(overrides)
    return LifeRatingInput(**base)


def test_life_older_applicant_pays_more() -> None:
    young = rate_life(_clean_life(age=30))
    older = rate_life(_clean_life(age=60))
    assert older.annual_premium > young.annual_premium


def test_life_tobacco_surcharge() -> None:
    non = rate_life(_clean_life())
    smoker = rate_life(_clean_life(tobacco_user=True))
    assert smoker.annual_premium > non.annual_premium


def test_life_whole_costs_more_than_term() -> None:
    term = rate_life(_clean_life(life_type=LifeType.term))
    whole = rate_life(_clean_life(life_type=LifeType.whole, term_years=None))
    assert whole.annual_premium > term.annual_premium


def test_life_female_discount() -> None:
    male = rate_life(_clean_life(is_female=False))
    female = rate_life(_clean_life(is_female=True))
    assert female.annual_premium < male.annual_premium


def test_life_hard_decline_over_75_large_term() -> None:
    result = rate_life(_clean_life(age=78, coverage_amount=Decimal("750000")))
    assert result.declined is True
    assert result.risk_tier == RiskTier.declined


def test_life_preferred_health_cheaper_than_substandard() -> None:
    preferred = rate_life(_clean_life(health_class=HealthClass.preferred_plus))
    substandard = rate_life(_clean_life(health_class=HealthClass.substandard))
    assert preferred.annual_premium < substandard.annual_premium


# --------------------------------------------------------------------------- #
# Dispatcher                                                                   #
# --------------------------------------------------------------------------- #
def test_rate_quote_dispatches_by_policy_type() -> None:
    auto = rate_quote(PolicyType.auto, _clean_auto())
    home = rate_quote(PolicyType.home, _clean_home())
    life = rate_quote(PolicyType.life, _clean_life())
    assert auto.annual_premium > 0
    assert home.annual_premium > 0
    assert life.annual_premium > 0


def test_rate_quote_rejects_mismatched_inputs() -> None:
    with pytest.raises(AssertionError):
        rate_quote(PolicyType.auto, _clean_home())


def test_factors_are_explainable() -> None:
    result = rate_auto(_clean_auto())
    names = {f.name for f in result.factors}
    assert {"state", "vehicle_type", "coverage_type", "driver_age", "credit"} <= names
