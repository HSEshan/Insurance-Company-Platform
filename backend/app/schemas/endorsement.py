"""Endorsement request/response schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EndorsementStatus, EndorsementType


class EndorsementCreate(BaseModel):
    type: EndorsementType
    effective_date: date
    description: str | None = Field(default=None, max_length=4000)
    premium_impact: Decimal = Field(
        default=Decimal("0"),
        description="Signed change to annual premium (+ increase / - decrease).",
    )


class EndorsementReject(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class EndorsementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    policy_id: uuid.UUID
    endorsement_number: str | None = None
    type: EndorsementType
    effective_date: date
    description: str | None = None
    premium_impact: Decimal | None = None
    status: EndorsementStatus
    requested_by: uuid.UUID | None = None
    approved_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
