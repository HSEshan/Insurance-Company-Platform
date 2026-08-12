"""Customer profile schemas with PII masking."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import RiskTier


class CustomerAddress(BaseModel):
    address_line1: str | None = Field(default=None, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, min_length=2, max_length=2)
    zip: str | None = Field(default=None, max_length=10)
    country: str = Field(default="US", min_length=2, max_length=2)


class CustomerCreate(CustomerAddress):
    # Account fields for the underlying user record.
    email: str
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=20)

    # Customer profile fields.
    date_of_birth: date
    ssn: str | None = Field(default=None, description="Full SSN; stored encrypted.")
    dl_number: str | None = Field(default=None, max_length=50)
    dl_state: str | None = Field(default=None, min_length=2, max_length=2)
    dl_expiry: date | None = None

    @field_validator("ssn")
    @classmethod
    def validate_ssn(cls, v: str | None) -> str | None:
        if v is None:
            return v
        digits = v.replace("-", "").strip()
        if not (digits.isdigit() and len(digits) == 9):
            raise ValueError("SSN must contain exactly 9 digits.")
        return digits


class CustomerUpdate(CustomerAddress):
    phone: str | None = Field(default=None, max_length=20)
    dl_number: str | None = Field(default=None, max_length=50)
    dl_state: str | None = Field(default=None, min_length=2, max_length=2)
    dl_expiry: date | None = None


class CustomerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    date_of_birth: date
    ssn_masked: str | None = None
    dl_number: str | None = None
    dl_state: str | None = None
    dl_expiry: date | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    country: str
    credit_score: int | None = None
    risk_tier: RiskTier | None = None
    created_at: datetime


class CustomerListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    city: str | None = None
    state: str | None = None
    risk_tier: RiskTier | None = None
    created_at: datetime
