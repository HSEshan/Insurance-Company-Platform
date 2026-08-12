"""Policy model and per-line-of-business detail tables."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import (
    AutoCoverageType,
    BeneficiaryRelationship,
    ConstructionType,
    EndorsementStatus,
    EndorsementType,
    HealthClass,
    LifeType,
    PaymentFrequency,
    PolicyStatus,
    PolicyType,
    PremiumMode,
    RoofType,
    VehicleType,
    VehicleUse,
)


class Policy(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "policies"

    policy_number: Mapped[str] = mapped_column(
        String(30), unique=True, index=True, nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    quote_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotes.id", ondelete="SET NULL")
    )
    policy_type: Mapped[PolicyType] = mapped_column(
        SQLEnum(PolicyType, name="policy_type"), nullable=False
    )
    status: Mapped[PolicyStatus] = mapped_column(
        SQLEnum(PolicyStatus, name="policy_status"),
        default=PolicyStatus.draft,
        nullable=False,
    )
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiration_date: Mapped[date] = mapped_column(Date, nullable=False)
    annual_premium: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payment_frequency: Mapped[PaymentFrequency] = mapped_column(
        SQLEnum(PaymentFrequency, name="payment_frequency"),
        default=PaymentFrequency.monthly,
        nullable=False,
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    underwriter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PolicyAutoDetails(Base, UUIDMixin):
    __tablename__ = "policy_auto_details"

    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policies.id", ondelete="CASCADE"), nullable=False
    )
    vin: Mapped[str] = mapped_column(String(17), nullable=False)
    make: Mapped[str | None] = mapped_column(String(80))
    model: Mapped[str | None] = mapped_column(String(80))
    year: Mapped[int | None] = mapped_column(SmallInteger)
    vehicle_type: Mapped[VehicleType | None] = mapped_column(
        SQLEnum(VehicleType, name="vehicle_type")
    )
    primary_use: Mapped[VehicleUse | None] = mapped_column(
        SQLEnum(VehicleUse, name="vehicle_use")
    )
    annual_mileage: Mapped[int | None] = mapped_column(Integer)
    garaging_zip: Mapped[str | None] = mapped_column(String(10))
    coverage_type: Mapped[AutoCoverageType | None] = mapped_column(
        SQLEnum(AutoCoverageType, name="auto_coverage_type")
    )
    liability_limit: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    collision_deductible: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    comprehensive_deductible: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    uninsured_motorist: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    roadside_assistance: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rental_reimbursement: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class PolicyHomeDetails(Base, UUIDMixin):
    __tablename__ = "policy_home_details"

    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policies.id", ondelete="CASCADE"), nullable=False
    )
    property_address_line1: Mapped[str | None] = mapped_column(String(255))
    property_address_line2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(2))
    zip: Mapped[str | None] = mapped_column(String(10))
    year_built: Mapped[int | None] = mapped_column(SmallInteger)
    square_footage: Mapped[int | None] = mapped_column(Integer)
    construction_type: Mapped[ConstructionType | None] = mapped_column(
        SQLEnum(ConstructionType, name="construction_type")
    )
    roof_type: Mapped[RoofType | None] = mapped_column(SQLEnum(RoofType, name="roof_type"))
    roof_year: Mapped[int | None] = mapped_column(SmallInteger)
    home_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    dwelling_coverage: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    personal_property_coverage: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    liability_coverage: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    deductible: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    flood_coverage: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    earthquake_coverage: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    home_business_coverage: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )


class PolicyLifeDetails(Base, UUIDMixin):
    __tablename__ = "policy_life_details"

    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policies.id", ondelete="CASCADE"), nullable=False
    )
    coverage_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    policy_term_years: Mapped[int | None] = mapped_column(SmallInteger)
    life_type: Mapped[LifeType | None] = mapped_column(SQLEnum(LifeType, name="life_type"))
    tobacco_user: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    health_class: Mapped[HealthClass | None] = mapped_column(
        SQLEnum(HealthClass, name="health_class")
    )
    premium_mode: Mapped[PremiumMode | None] = mapped_column(
        SQLEnum(PremiumMode, name="premium_mode")
    )


class Beneficiary(Base, UUIDMixin):
    __tablename__ = "beneficiaries"

    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policies.id", ondelete="CASCADE"), nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    relationship_type: Mapped[BeneficiaryRelationship | None] = mapped_column(
        SQLEnum(BeneficiaryRelationship, name="beneficiary_relationship")
    )
    allocation_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    ssn_last4: Mapped[str | None] = mapped_column(String(4))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    is_contingent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Endorsement(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "endorsements"

    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policies.id", ondelete="CASCADE"), nullable=False
    )
    endorsement_number: Mapped[str | None] = mapped_column(String(20))
    type: Mapped[EndorsementType] = mapped_column(
        SQLEnum(EndorsementType, name="endorsement_type"), nullable=False
    )
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    premium_impact: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    status: Mapped[EndorsementStatus] = mapped_column(
        SQLEnum(EndorsementStatus, name="endorsement_status"),
        default=EndorsementStatus.pending,
        nullable=False,
    )
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
