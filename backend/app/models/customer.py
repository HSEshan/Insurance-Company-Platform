"""Customer profile model (extends a user with role=customer)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, SmallInteger, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import RiskTier

if TYPE_CHECKING:
    from app.models.user import User


class Customer(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "customers"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)

    # SSN is never stored in the clear: last 4 for display, full value encrypted.
    ssn_last4: Mapped[str | None] = mapped_column(String(4))
    ssn_encrypted: Mapped[str | None] = mapped_column(String)

    dl_number: Mapped[str | None] = mapped_column(String(50))
    dl_state: Mapped[str | None] = mapped_column(String(2))
    dl_expiry: Mapped[date | None] = mapped_column(Date)

    address_line1: Mapped[str | None] = mapped_column(String(255))
    address_line2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(2))
    zip: Mapped[str | None] = mapped_column(String(10))
    country: Mapped[str] = mapped_column(String(2), default="US", nullable=False)

    credit_score: Mapped[int | None] = mapped_column(SmallInteger)
    risk_tier: Mapped[RiskTier | None] = mapped_column(SQLEnum(RiskTier, name="risk_tier"))

    user: Mapped[User] = relationship(back_populates="customer")
