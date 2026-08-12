"""Claim request/response schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ClaimNoteType, ClaimStatus, ClaimType


class ClaimCreate(BaseModel):
    policy_id: uuid.UUID
    claim_type: ClaimType
    incident_date: date
    description: str = Field(min_length=10, max_length=10000)
    incident_location: str | None = Field(default=None, max_length=500)
    estimated_damage: Decimal | None = Field(default=None, ge=0)


class ClaimAssign(BaseModel):
    adjuster_id: uuid.UUID


class ClaimApprove(BaseModel):
    approved_amount: Decimal = Field(gt=0)


class ClaimReject(BaseModel):
    reason: str = Field(min_length=1, max_length=4000)


class ClaimDispute(BaseModel):
    reason: str = Field(min_length=1, max_length=4000)


class ClaimResolveDispute(BaseModel):
    uphold_rejection: bool = Field(
        description="True = keep rejected; False = override to approved."
    )
    approved_amount: Decimal | None = Field(
        default=None,
        gt=0,
        description="Required when overturning a rejection.",
    )


class ClaimNoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=10000)
    note_type: ClaimNoteType = ClaimNoteType.internal
    is_visible_to_customer: bool = False


class ClaimNoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    claim_id: uuid.UUID
    author_id: uuid.UUID | None = None
    note_type: ClaimNoteType
    body: str
    is_visible_to_customer: bool
    created_at: datetime


class ClaimListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    claim_number: str
    policy_id: uuid.UUID
    customer_id: uuid.UUID
    claim_type: ClaimType
    status: ClaimStatus
    incident_date: date
    estimated_damage: Decimal | None = None
    approved_amount: Decimal | None = None
    fraud_flag: bool
    adjuster_id: uuid.UUID | None = None
    created_at: datetime


class ClaimRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    claim_number: str
    policy_id: uuid.UUID
    customer_id: uuid.UUID
    claim_type: ClaimType
    incident_date: date
    reported_date: date
    description: str
    incident_location: str | None = None
    estimated_damage: Decimal | None = None
    approved_amount: Decimal | None = None
    final_payout: Decimal | None = None
    status: ClaimStatus
    fraud_flag: bool
    fraud_score: Decimal | None = None
    adjuster_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    notes: list[ClaimNoteRead] = []
