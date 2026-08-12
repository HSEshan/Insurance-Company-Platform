"""Validated inputs for each rating line of business."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import (
    AutoCoverageType,
    ConstructionType,
    HealthClass,
    LifeType,
    VehicleType,
)


class AutoRatingInput(BaseModel):
    state: str = Field(min_length=2, max_length=2)
    driver_age: int = Field(ge=16, le=110)
    vehicle_type: VehicleType = VehicleType.sedan
    vehicle_year: int = Field(ge=1950, le=2100)
    coverage_type: AutoCoverageType = AutoCoverageType.full_coverage
    annual_mileage: int = Field(default=12000, ge=0, le=200000)
    collision_deductible: Decimal = Field(default=Decimal("500"), ge=0)
    dui_count: int = Field(default=0, ge=0)
    speeding_violations: int = Field(default=0, ge=0)
    at_fault_claims_3yr: int = Field(default=0, ge=0)
    credit_score: int = Field(default=700, ge=300, le=850)
    has_existing_home_policy: bool = False
    anti_theft_device: bool = False


class HomeRatingInput(BaseModel):
    state: str = Field(min_length=2, max_length=2)
    dwelling_coverage: Decimal = Field(gt=0)
    year_built: int = Field(ge=1800, le=2100)
    roof_year: int = Field(ge=1800, le=2100)
    construction_type: ConstructionType = ConstructionType.frame
    deductible: Decimal = Field(default=Decimal("1000"), ge=0)
    claims_3yr: int = Field(default=0, ge=0)
    in_flood_zone: bool = False
    has_flood_rider: bool = False
    has_security_system: bool = False
    credit_score: int = Field(default=700, ge=300, le=850)


class LifeRatingInput(BaseModel):
    age: int = Field(ge=18, le=85)
    coverage_amount: Decimal = Field(gt=0)
    life_type: LifeType = LifeType.term
    term_years: int | None = Field(default=20, ge=5, le=40)
    is_female: bool = False
    tobacco_user: bool = False
    health_class: HealthClass = HealthClass.standard
