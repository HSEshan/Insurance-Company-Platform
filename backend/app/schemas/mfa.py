"""Contact verification and two-factor authentication schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import MfaMethod


class CodeDispatch(BaseModel):
    """Where a one-time code was sent. ``simulated_code`` is populated only when a
    simulated provider handled delivery and ``OTP_EXPOSE_SIMULATED_CODES`` is on."""

    channel: Literal["email", "sms"]
    destination: str  # masked
    expires_in_seconds: int
    resend_after_seconds: int
    simulated: bool = False
    simulated_code: str | None = None


class VerifyCodeRequest(BaseModel):
    code: str = Field(min_length=4, max_length=16)


class PhoneVerificationRequest(BaseModel):
    # Omit to verify the number already on file; send one to change it (the new
    # number is only saved once the code is confirmed).
    phone: str | None = Field(default=None, max_length=20)


class PasswordConfirmRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class EnableOtpMfaRequest(PasswordConfirmRequest):
    method: Literal[MfaMethod.email, MfaMethod.sms]


class SecurityStatus(BaseModel):
    email: str
    email_verified: bool
    email_verified_at: datetime | None = None
    phone: str | None = None
    phone_verified: bool
    phone_verified_at: datetime | None = None
    mfa_enabled: bool
    mfa_method: MfaMethod | None = None
    mfa_enabled_at: datetime | None = None
    recovery_codes_remaining: int = 0
    # Methods the user could switch to right now (channel verified etc.).
    available_methods: list[MfaMethod] = []
    # Set when 2FA changes are blocked (shared demo accounts).
    mfa_locked_reason: str | None = None


class TotpSetup(BaseModel):
    secret: str
    otpauth_uri: str
    qr_code_data_uri: str
    expires_in_seconds: int


class RecoveryCodesResult(BaseModel):
    """Plaintext recovery codes are returned exactly once."""

    recovery_codes: list[str]
    status: SecurityStatus


class MfaChallenge(BaseModel):
    mfa_token: str
    method: MfaMethod
    destination: str | None = None  # masked email/phone for email/sms methods
    expires_in_seconds: int
    dispatch: CodeDispatch | None = None


class MfaVerifyRequest(BaseModel):
    mfa_token: str
    # Six-digit code, or a recovery code (``xxxxx-xxxxx``).
    code: str = Field(min_length=4, max_length=16)


class MfaResendRequest(BaseModel):
    mfa_token: str
