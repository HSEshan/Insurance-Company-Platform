"""Payment request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PaymentMethod, PaymentStatus, PaymentType


class PaymentCreate(BaseModel):
    """Record a premium payment against one installment of a schedule."""

    schedule_id: uuid.UUID
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    method: PaymentMethod
    # Required for check and wire, where the number comes off the instrument
    # itself. Generated for the simulated electronic methods.
    reference_number: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=1000)


class PaymentVoid(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    schedule_id: uuid.UUID | None = None
    claim_id: uuid.UUID | None = None
    customer_id: uuid.UUID
    payment_type: PaymentType
    amount: Decimal
    currency: str
    method: PaymentMethod | None = None
    status: PaymentStatus
    reference_number: str | None = None
    processed_at: datetime | None = None
    notes: str | None = None
    created_at: datetime

    # Denormalized for list views so the UI does not need a lookup per row.
    policy_number: str | None = None
    claim_number: str | None = None
    customer_name: str | None = None
