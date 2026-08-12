"""The deterministic premium rating engine.

Every calculation returns an explainable :class:`RatingResult` listing the base
premium and each named multiplicative factor that was applied.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from functools import reduce

from app.models.enums import LifeType, PolicyType, RiskTier
from app.services.rating import tables
from app.services.rating.inputs import (
    AutoRatingInput,
    HomeRatingInput,
    LifeRatingInput,
)
from app.services.rating.result import RatingFactor, RatingResult

# Reference year used for age-based factors so results are deterministic.
REFERENCE_YEAR = 2026

_CENTS = Decimal("0.01")


def _money(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(_CENTS, rounding=ROUND_HALF_UP)


def _credit_factor(credit_score: int) -> float:
    if credit_score >= 800:
        return 0.85
    if credit_score >= 720:
        return 0.95
    if credit_score >= 660:
        return 1.0
    if credit_score >= 600:
        return 1.15
    return 1.30


def _risk_tier(total_factor: float) -> RiskTier:
    if total_factor <= 0.95:
        return RiskTier.preferred
    if total_factor <= 1.30:
        return RiskTier.standard
    return RiskTier.substandard


def _finalize(
    base: float,
    factors: list[RatingFactor],
    *,
    declined: bool = False,
    decline_reasons: list[str] | None = None,
) -> RatingResult:
    total_factor = reduce(lambda acc, f: acc * f.multiplier, factors, 1.0)
    annual = _money(base * total_factor)
    monthly = _money(annual / Decimal(12))
    tier = RiskTier.declined if declined else _risk_tier(total_factor)
    return RatingResult(
        base_premium=_money(base),
        factors=factors,
        annual_premium=annual,
        monthly_premium=monthly,
        risk_tier=tier,
        declined=declined,
        decline_reasons=decline_reasons or [],
    )


# --------------------------------------------------------------------------- #
# Auto                                                                         #
# --------------------------------------------------------------------------- #
def _auto_age_factor(age: int) -> float:
    if age < 20:
        return 1.8
    if age < 25:
        return 1.5
    if age < 30:
        return 1.15
    if age < 65:
        return 1.0
    if age < 75:
        return 1.1
    return 1.35


def _auto_mileage_factor(mileage: int) -> float:
    if mileage < 7500:
        return 0.9
    if mileage <= 15000:
        return 1.0
    return 1.15


def _auto_deductible_factor(deductible: Decimal) -> float:
    if deductible <= 250:
        return 1.1
    if deductible < 1000:
        return 1.0
    if deductible < 2000:
        return 0.92
    return 0.85


def rate_auto(inp: AutoRatingInput) -> RatingResult:
    factors: list[RatingFactor] = [
        RatingFactor(
            name="state",
            multiplier=tables.AUTO_STATE_FACTOR.get(
                inp.state.upper(), tables.AUTO_STATE_FACTOR_DEFAULT
            ),
        ),
        RatingFactor(
            name="vehicle_type",
            multiplier=tables.AUTO_VEHICLE_FACTOR[inp.vehicle_type],
        ),
        RatingFactor(
            name="coverage_type",
            multiplier=tables.AUTO_COVERAGE_FACTOR[inp.coverage_type],
        ),
        RatingFactor(name="driver_age", multiplier=_auto_age_factor(inp.driver_age)),
        RatingFactor(name="mileage", multiplier=_auto_mileage_factor(inp.annual_mileage)),
        RatingFactor(
            name="deductible",
            multiplier=_auto_deductible_factor(inp.collision_deductible),
        ),
        RatingFactor(name="credit", multiplier=_credit_factor(inp.credit_score)),
    ]

    if REFERENCE_YEAR - inp.vehicle_year <= 3:
        factors.append(RatingFactor(name="new_vehicle", multiplier=1.1))

    if inp.dui_count:
        factors.append(
            RatingFactor(
                name="dui_surcharge",
                multiplier=1.0 + inp.dui_count * tables.AUTO_DUI_SURCHARGE,
            )
        )
    if inp.speeding_violations:
        factors.append(
            RatingFactor(
                name="speeding_surcharge",
                multiplier=1.0
                + inp.speeding_violations * tables.AUTO_SPEEDING_SURCHARGE,
            )
        )
    if inp.at_fault_claims_3yr:
        factors.append(
            RatingFactor(
                name="claims_surcharge",
                multiplier=1.0
                + inp.at_fault_claims_3yr * tables.AUTO_AT_FAULT_CLAIM_SURCHARGE,
            )
        )
    if inp.anti_theft_device:
        factors.append(RatingFactor(name="anti_theft_discount", multiplier=0.97))
    if inp.has_existing_home_policy:
        factors.append(RatingFactor(name="multi_policy_discount", multiplier=0.9))

    declined = inp.dui_count > 0 and inp.at_fault_claims_3yr > 2
    reasons = (
        ["DUI on record with more than two at-fault claims in the last 3 years."]
        if declined
        else []
    )
    return _finalize(
        tables.AUTO_BASE_PREMIUM, factors, declined=declined, decline_reasons=reasons
    )


# --------------------------------------------------------------------------- #
# Home                                                                         #
# --------------------------------------------------------------------------- #
def _home_roof_factor(roof_year: int) -> float:
    age = REFERENCE_YEAR - roof_year
    if age <= 10:
        return 1.0
    if age <= 20:
        return 1.1
    return 1.3


def _home_deductible_factor(deductible: Decimal) -> float:
    if deductible < 1000:
        return 1.1
    if deductible < 2500:
        return 1.0
    if deductible < 5000:
        return 0.9
    return 0.82


def rate_home(inp: HomeRatingInput) -> RatingResult:
    base = float(inp.dwelling_coverage) / 1000.0 * tables.HOME_RATE_PER_1000

    factors: list[RatingFactor] = [
        RatingFactor(
            name="state",
            multiplier=tables.HOME_STATE_FACTOR.get(
                inp.state.upper(), tables.HOME_STATE_FACTOR_DEFAULT
            ),
        ),
        RatingFactor(
            name="construction_type",
            multiplier=tables.HOME_CONSTRUCTION_FACTOR[inp.construction_type],
        ),
        RatingFactor(name="roof_age", multiplier=_home_roof_factor(inp.roof_year)),
        RatingFactor(
            name="deductible", multiplier=_home_deductible_factor(inp.deductible)
        ),
        RatingFactor(name="credit", multiplier=_credit_factor(inp.credit_score)),
    ]

    if REFERENCE_YEAR - inp.year_built > 50:
        factors.append(RatingFactor(name="older_home", multiplier=1.15))
    if inp.claims_3yr:
        factors.append(
            RatingFactor(
                name="claims_surcharge",
                multiplier=1.0 + inp.claims_3yr * tables.HOME_CLAIM_SURCHARGE,
            )
        )
    if inp.in_flood_zone:
        factors.append(
            RatingFactor(
                name="flood_surcharge",
                multiplier=1.0 + tables.HOME_FLOOD_SURCHARGE,
            )
        )
    if inp.has_security_system:
        factors.append(RatingFactor(name="security_discount", multiplier=0.95))

    declined = inp.in_flood_zone and not inp.has_flood_rider
    reasons = (
        [
            "Property in a FEMA flood zone requires a separate flood rider "
            "before homeowners coverage can be issued."
        ]
        if declined
        else []
    )
    return _finalize(base, factors, declined=declined, decline_reasons=reasons)


# --------------------------------------------------------------------------- #
# Life                                                                         #
# --------------------------------------------------------------------------- #
def _life_term_factor(term_years: int | None) -> float:
    if term_years is None:
        return 1.0
    if term_years <= 10:
        return 1.0
    if term_years <= 15:
        return 1.1
    if term_years <= 20:
        return 1.25
    if term_years <= 30:
        return 1.6
    return 2.0


def rate_life(inp: LifeRatingInput) -> RatingResult:
    mortality = tables.lookup_life_mortality(inp.age)
    base = float(inp.coverage_amount) / 1000.0 * mortality

    factors: list[RatingFactor] = [
        RatingFactor(
            name="life_type", multiplier=tables.LIFE_TYPE_FACTOR[inp.life_type]
        ),
        RatingFactor(
            name="health_class", multiplier=tables.LIFE_HEALTH_FACTOR[inp.health_class]
        ),
    ]

    if inp.life_type == LifeType.term:
        factors.append(
            RatingFactor(name="term_length", multiplier=_life_term_factor(inp.term_years))
        )
    if inp.is_female:
        factors.append(
            RatingFactor(name="gender", multiplier=tables.LIFE_FEMALE_FACTOR)
        )
    if inp.tobacco_user:
        factors.append(
            RatingFactor(
                name="tobacco_surcharge",
                multiplier=1.0 + tables.LIFE_TOBACCO_SURCHARGE,
            )
        )

    declined = (
        inp.age > 75
        and inp.coverage_amount > Decimal("500000")
        and inp.life_type == LifeType.term
    )
    reasons = (
        ["New term life over $500K is not offered above age 75."] if declined else []
    )
    return _finalize(base, factors, declined=declined, decline_reasons=reasons)


# --------------------------------------------------------------------------- #
# Dispatcher                                                                   #
# --------------------------------------------------------------------------- #
def rate_quote(
    policy_type: PolicyType,
    inputs: AutoRatingInput | HomeRatingInput | LifeRatingInput,
) -> RatingResult:
    if policy_type == PolicyType.auto:
        assert isinstance(inputs, AutoRatingInput)
        return rate_auto(inputs)
    if policy_type == PolicyType.home:
        assert isinstance(inputs, HomeRatingInput)
        return rate_home(inputs)
    if policy_type == PolicyType.life:
        assert isinstance(inputs, LifeRatingInput)
        return rate_life(inputs)
    raise ValueError(f"Unsupported policy type: {policy_type}")
