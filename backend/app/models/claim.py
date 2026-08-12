"""Claim and claim note models."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import ClaimNoteType, ClaimStatus, ClaimType


class Claim(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "claims"

    claim_number: Mapped[str] = mapped_column(
        String(30), unique=True, index=True, nullable=False
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policies.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    claim_type: Mapped[ClaimType] = mapped_column(
        SQLEnum(ClaimType, name="claim_type"), nullable=False
    )
    incident_date: Mapped[date] = mapped_column(Date, nullable=False)
    reported_date: Mapped[date] = mapped_column(
        Date, server_default=func.current_date(), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    incident_location: Mapped[str | None] = mapped_column(Text)
    estimated_damage: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    approved_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    final_payout: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    status: Mapped[ClaimStatus] = mapped_column(
        SQLEnum(ClaimStatus, name="claim_status"),
        default=ClaimStatus.submitted,
        nullable=False,
    )
    fraud_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fraud_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    adjuster_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class ClaimNote(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "claim_notes"

    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    note_type: Mapped[ClaimNoteType] = mapped_column(
        SQLEnum(ClaimNoteType, name="claim_note_type"),
        default=ClaimNoteType.internal,
        nullable=False,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_visible_to_customer: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
