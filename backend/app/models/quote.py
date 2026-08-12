"""Insurance quote model."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, ForeignKey, Numeric, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import PolicyType, QuoteStatus, RiskTier


class Quote(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "quotes"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    policy_type: Mapped[PolicyType] = mapped_column(
        SQLEnum(PolicyType, name="policy_type"), nullable=False
    )
    status: Mapped[QuoteStatus] = mapped_column(
        SQLEnum(QuoteStatus, name="quote_status"),
        default=QuoteStatus.draft,
        nullable=False,
    )
    quoted_premium: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    monthly_premium: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    risk_tier: Mapped[RiskTier | None] = mapped_column(
        SQLEnum(RiskTier, name="risk_tier", create_type=False)
    )
    # Snapshot of rating inputs / factor breakdown / LOB details for bind-time use.
    rating_inputs: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    rating_factors: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    policy_details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    decline_reasons: Mapped[list[str] | None] = mapped_column(JSONB)
    effective_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    underwriter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text)
