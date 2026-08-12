"""Super-Admin staff / employee management schemas."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.enums import UserRole
from app.schemas.user import UserRead

STAFF_ROLES = frozenset(
    {
        UserRole.agent,
        UserRole.adjuster,
        UserRole.manager,
        UserRole.super_admin,
    }
)


class StaffCreate(BaseModel):
    email: EmailStr
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    role: UserRole

    @field_validator("role")
    @classmethod
    def role_must_be_staff(cls, value: UserRole) -> UserRole:
        if value not in STAFF_ROLES:
            raise ValueError("Staff accounts cannot have the customer role.")
        return value


class StaffUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    role: UserRole | None = None
    # Required when the update would leave open work without an owner.
    reassign_agent_id: uuid.UUID | None = None
    reassign_adjuster_id: uuid.UUID | None = None

    @field_validator("role")
    @classmethod
    def role_must_be_staff(cls, value: UserRole | None) -> UserRole | None:
        if value is not None and value not in STAFF_ROLES:
            raise ValueError("Staff accounts cannot have the customer role.")
        return value


class StaffDeactivate(BaseModel):
    reassign_agent_id: uuid.UUID | None = None
    reassign_adjuster_id: uuid.UUID | None = None


class StaffCreateResult(BaseModel):
    user: UserRead
    temporary_password: str
    email_sent: bool


class OpenWorkSummary(BaseModel):
    policies: int
    open_claims: int
    requires_agent_reassign: bool
    requires_adjuster_reassign: bool
