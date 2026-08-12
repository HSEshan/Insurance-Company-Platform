"""Static actuarial tables and rating constants.

These are illustrative, simplified stand-ins for the rate tables a real carrier
would file with state regulators. They exist to make the engine deterministic
and explainable, not to be actuarially sound.
"""

from __future__ import annotations

from app.models.enums import (
    AutoCoverageType,
    ConstructionType,
    HealthClass,
    LifeType,
    VehicleType,
)

# --------------------------------------------------------------------------- #
# Auto                                                                         #
# --------------------------------------------------------------------------- #
AUTO_BASE_PREMIUM = 900.0

# Per-state base multiplier (loss-cost proxy). Unlisted states use the default.
AUTO_STATE_FACTOR: dict[str, float] = {
    "CA": 1.25,
    "NY": 1.30,
    "FL": 1.35,
    "TX": 1.10,
    "MI": 1.45,
    "OH": 0.95,
    "IA": 0.85,
    "ME": 0.80,
}
AUTO_STATE_FACTOR_DEFAULT = 1.0

AUTO_VEHICLE_FACTOR: dict[VehicleType, float] = {
    VehicleType.sedan: 1.0,
    VehicleType.suv: 1.1,
    VehicleType.truck: 1.15,
    VehicleType.motorcycle: 1.4,
    VehicleType.commercial: 1.6,
}

AUTO_COVERAGE_FACTOR: dict[AutoCoverageType, float] = {
    AutoCoverageType.liability_only: 0.65,
    AutoCoverageType.collision: 0.85,
    AutoCoverageType.comprehensive: 0.9,
    AutoCoverageType.full_coverage: 1.0,
}

# Surcharge per violation / claim.
AUTO_DUI_SURCHARGE = 0.50
AUTO_SPEEDING_SURCHARGE = 0.15
AUTO_AT_FAULT_CLAIM_SURCHARGE = 0.15

# --------------------------------------------------------------------------- #
# Home                                                                         #
# --------------------------------------------------------------------------- #
# Base rate expressed as premium per $1,000 of dwelling coverage.
HOME_RATE_PER_1000 = 3.5

HOME_STATE_FACTOR: dict[str, float] = {
    "FL": 1.6,
    "TX": 1.25,
    "CA": 1.2,
    "LA": 1.7,
    "OK": 1.4,
    "OH": 0.9,
    "IL": 0.95,
}
HOME_STATE_FACTOR_DEFAULT = 1.0

HOME_CONSTRUCTION_FACTOR: dict[ConstructionType, float] = {
    ConstructionType.frame: 1.0,
    ConstructionType.masonry: 0.9,
    ConstructionType.manufactured: 1.3,
}

HOME_CLAIM_SURCHARGE = 0.12
HOME_FLOOD_SURCHARGE = 0.25

# --------------------------------------------------------------------------- #
# Life                                                                         #
# --------------------------------------------------------------------------- #
# Annual base cost per $1,000 of coverage by age band (simplified mortality).
LIFE_MORTALITY_PER_1000: list[tuple[int, int, float]] = [
    (18, 29, 0.8),
    (30, 39, 1.0),
    (40, 49, 1.9),
    (50, 59, 3.8),
    (60, 69, 8.5),
    (70, 85, 18.0),
]

LIFE_HEALTH_FACTOR: dict[HealthClass, float] = {
    HealthClass.preferred_plus: 0.75,
    HealthClass.preferred: 0.9,
    HealthClass.standard_plus: 1.0,
    HealthClass.standard: 1.1,
    HealthClass.substandard: 1.75,
}

LIFE_TYPE_FACTOR: dict[LifeType, float] = {
    LifeType.term: 1.0,
    LifeType.whole: 2.6,
    LifeType.universal: 2.2,
}

LIFE_TOBACCO_SURCHARGE = 0.5
LIFE_FEMALE_FACTOR = 0.9


def lookup_life_mortality(age: int) -> float:
    for low, high, rate in LIFE_MORTALITY_PER_1000:
        if low <= age <= high:
            return rate
    # Ages above the last band fall back to its rate.
    return LIFE_MORTALITY_PER_1000[-1][2]
