"""Policy request/response schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    PaymentFrequency,
    PolicyStatus,
    PolicyType,
    PremiumScheduleStatus,
)


class PolicyCancel(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class PolicyBindRequest(BaseModel):
    payment_frequency: PaymentFrequency = PaymentFrequency.monthly


class PremiumScheduleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    policy_id: uuid.UUID
    due_date: date
    amount_due: Decimal
    status: PremiumScheduleStatus
    created_at: datetime

    # Derived from completed payments rather than stored, so the ledger and the
    # installment can never disagree. Partial payments leave a balance.
    amount_paid: Decimal = Decimal("0.00")
    balance: Decimal = Decimal("0.00")


class BeneficiaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    relationship_type: str | None = None
    allocation_pct: Decimal
    ssn_last4: str | None = None
    date_of_birth: date | None = None
    is_contingent: bool


class PolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    policy_number: str
    customer_id: uuid.UUID
    quote_id: uuid.UUID | None = None
    policy_type: PolicyType
    status: PolicyStatus
    effective_date: date
    expiration_date: date
    annual_premium: Decimal
    payment_frequency: PaymentFrequency
    agent_id: uuid.UUID | None = None
    underwriter_id: uuid.UUID | None = None
    cancellation_reason: str | None = None
    cancelled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    # Nested LOB detail (one of these populated depending on policy_type).
    auto_details: dict[str, Any] | None = None
    home_details: dict[str, Any] | None = None
    life_details: dict[str, Any] | None = None
    beneficiaries: list[BeneficiaryRead] = []
    premium_schedules: list[PremiumScheduleRead] = []


class PolicyListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    policy_number: str
    customer_id: uuid.UUID
    policy_type: PolicyType
    status: PolicyStatus
    effective_date: date
    expiration_date: date
    annual_premium: Decimal
    payment_frequency: PaymentFrequency
    created_at: datetime
