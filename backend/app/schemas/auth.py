"""Authentication request/response schemas."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, EmailStr, Field

from app.schemas.mfa import MfaChallenge
from app.schemas.user import UserRead


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    date_of_birth: date


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class AuthResult(BaseModel):
    user: UserRead
    tokens: TokenPair


class LoginResult(BaseModel):
    """Either a full session (``user`` + ``tokens``) or, when the account has 2FA,
    a ``challenge`` to complete via ``POST /auth/mfa/verify``."""

    mfa_required: bool = False
    user: UserRead | None = None
    tokens: TokenPair | None = None
    challenge: MfaChallenge | None = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)
