"""User account model (all roles)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import MfaMethod, UserRole

if TYPE_CHECKING:
    from app.models.customer import Customer


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole, name="user_role"),
        default=UserRole.customer,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Set when Super Admin issues a temp password; cleared after the employee
    # chooses their own via POST /auth/change-password.
    must_reset_password: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- Contact verification (cleared whenever the address/number changes) ---
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- Two-factor authentication ---
    # NULL = 2FA off. Email/SMS require the matching channel to be verified.
    mfa_method: Mapped[MfaMethod | None] = mapped_column(
        SQLEnum(MfaMethod, name="mfa_method")
    )
    mfa_enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Fernet-encrypted base32 TOTP secret (set only once enrollment is confirmed).
    totp_secret_encrypted: Mapped[str | None] = mapped_column(String)
    # SHA-256 hashes of unused single-use recovery codes.
    mfa_recovery_codes: Mapped[list[str] | None] = mapped_column(JSONB)

    customer: Mapped[Customer | None] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None

    @property
    def phone_verified(self) -> bool:
        return self.phone_verified_at is not None

    @property
    def mfa_enabled(self) -> bool:
        return self.mfa_method is not None
