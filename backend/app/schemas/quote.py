"""Quote request/response schemas and LOB detail payloads."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    AutoCoverageType,
    BeneficiaryRelationship,
    ConstructionType,
    HealthClass,
    LifeType,
    PolicyType,
    PremiumMode,
    QuoteStatus,
    RiskTier,
    RoofType,
    VehicleType,
    VehicleUse,
)
from app.services.rating.inputs import AutoRatingInput, HomeRatingInput, LifeRatingInput
from app.services.rating.result import RatingFactor


# --------------------------------------------------------------------------- #
# Policy detail payloads stored on the quote and copied at bind time
# --------------------------------------------------------------------------- #
class AutoDetailsCreate(BaseModel):
    vin: str = Field(min_length=11, max_length=17)
    make: str | None = Field(default=None, max_length=80)
    model: str | None = Field(default=None, max_length=80)
    year: int | None = Field(default=None, ge=1950, le=2100)
    vehicle_type: VehicleType = VehicleType.sedan
    primary_use: VehicleUse = VehicleUse.personal
    annual_mileage: int = Field(default=12000, ge=0, le=200000)
    garaging_zip: str | None = Field(default=None, max_length=10)
    coverage_type: AutoCoverageType = AutoCoverageType.full_coverage
    liability_limit: Decimal | None = Field(default=Decimal("100000"), ge=0)
    collision_deductible: Decimal = Field(default=Decimal("500"), ge=0)
    comprehensive_deductible: Decimal = Field(default=Decimal("500"), ge=0)
    uninsured_motorist: bool = False
    roadside_assistance: bool = False
    rental_reimbursement: bool = False


class HomeDetailsCreate(BaseModel):
    property_address_line1: str = Field(min_length=1, max_length=255)
    property_address_line2: str | None = Field(default=None, max_length=255)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=2, max_length=2)
    zip: str = Field(min_length=5, max_length=10)
    year_built: int = Field(ge=1800, le=2100)
    square_footage: int | None = Field(default=None, ge=100, le=100000)
    construction_type: ConstructionType = ConstructionType.frame
    roof_type: RoofType = RoofType.shingle
    roof_year: int = Field(ge=1800, le=2100)
    home_value: Decimal | None = Field(default=None, ge=0)
    dwelling_coverage: Decimal = Field(gt=0)
    personal_property_coverage: Decimal | None = Field(default=None, ge=0)
    liability_coverage: Decimal | None = Field(default=None, ge=0)
    deductible: Decimal = Field(default=Decimal("1000"), ge=0)
    flood_coverage: bool = False
    earthquake_coverage: bool = False
    home_business_coverage: bool = False


class BeneficiaryCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    relationship: BeneficiaryRelationship = BeneficiaryRelationship.other
    allocation_pct: Decimal = Field(gt=0, le=100)
    ssn_last4: str | None = Field(default=None, min_length=4, max_length=4)
    date_of_birth: date | None = None
    is_contingent: bool = False


class LifeDetailsCreate(BaseModel):
    coverage_amount: Decimal = Field(gt=0)
    policy_term_years: int | None = Field(default=20, ge=5, le=40)
    life_type: LifeType = LifeType.term
    tobacco_user: bool = False
    health_class: HealthClass = HealthClass.standard
    premium_mode: PremiumMode = PremiumMode.level
    beneficiaries: list[BeneficiaryCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def allocations_sum_to_100(self) -> LifeDetailsCreate:
        primaries = [b for b in self.beneficiaries if not b.is_contingent]
        if not primaries:
            return self
        total = sum((b.allocation_pct for b in primaries), Decimal("0"))
        if total != Decimal("100"):
            raise ValueError("Primary beneficiary allocations must sum to 100.")
        return self


# --------------------------------------------------------------------------- #
# Quote create / update
# --------------------------------------------------------------------------- #
class QuoteCreate(BaseModel):
    """Create a persisted quote. Exactly one LOB rating+details block is required."""

    customer_id: uuid.UUID | None = None
    policy_type: PolicyType
    effective_date: date
    notes: str | None = None

    auto_rating: AutoRatingInput | None = None
    auto_details: AutoDetailsCreate | None = None
    home_rating: HomeRatingInput | None = None
    home_details: HomeDetailsCreate | None = None
    life_rating: LifeRatingInput | None = None
    life_details: LifeDetailsCreate | None = None

    @model_validator(mode="after")
    def require_matching_lob_payload(self) -> QuoteCreate:
        pairs = {
            PolicyType.auto: (self.auto_rating, self.auto_details),
            PolicyType.home: (self.home_rating, self.home_details),
            PolicyType.life: (self.life_rating, self.life_details),
        }
        rating, details = pairs[self.policy_type]
        if rating is None or details is None:
            raise ValueError(
                f"{self.policy_type.value}_rating and {self.policy_type.value}_details "
                "are required for this policy type."
            )
        return self


class QuoteUpdate(BaseModel):
    """Patch a draft quote. Only provided fields are applied."""

    effective_date: date | None = None
    notes: str | None = None
    auto_rating: AutoRatingInput | None = None
    auto_details: AutoDetailsCreate | None = None
    home_rating: HomeRatingInput | None = None
    home_details: HomeDetailsCreate | None = None
    life_rating: LifeRatingInput | None = None
    life_details: LifeDetailsCreate | None = None


class QuoteReject(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


# --------------------------------------------------------------------------- #
# Read models
# --------------------------------------------------------------------------- #
class QuoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    policy_type: PolicyType
    status: QuoteStatus
    quoted_premium: Decimal | None = None
    monthly_premium: Decimal | None = None
    risk_tier: RiskTier | None = None
    rating_inputs: dict[str, Any] | None = None
    rating_factors: list[RatingFactor] | None = None
    policy_details: dict[str, Any] | None = None
    decline_reasons: list[str] | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    agent_id: uuid.UUID | None = None
    underwriter_id: uuid.UUID | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class QuoteListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    policy_type: PolicyType
    status: QuoteStatus
    quoted_premium: Decimal | None = None
    risk_tier: RiskTier | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    created_at: datetime
