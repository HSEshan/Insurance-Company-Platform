"""Security primitives: password hashing, JWT tokens, and PII encryption."""

from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

TokenType = Literal["access", "refresh"]


# --------------------------------------------------------------------------- #
# Password hashing (bcrypt)                                                    #
# --------------------------------------------------------------------------- #
def hash_password(plain_password: str) -> str:
    # bcrypt has a hard 72-byte limit; encode and let bcrypt handle salting.
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except ValueError:
        return False


# --------------------------------------------------------------------------- #
# JWT token creation / decoding                                                #
# --------------------------------------------------------------------------- #
def _create_token(
    subject: str,
    token_type: TokenType,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        "jti": str(uuid.uuid4()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(
    subject: str, extra_claims: dict[str, Any] | None = None
) -> str:
    return _create_token(
        subject,
        "access",
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        extra_claims,
    )


def create_refresh_token(subject: str) -> str:
    return _create_token(
        subject,
        "refresh",
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT. Raises jwt.PyJWTError on any failure."""
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )


# --------------------------------------------------------------------------- #
# Application-layer PII encryption (AES via Fernet)                            #
# --------------------------------------------------------------------------- #
def _fernet() -> Fernet:
    # Derive a deterministic, valid 32-byte Fernet key from the configured key.
    digest = hashlib.sha256(settings.ENCRYPTION_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_pii(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_pii(token: str | None) -> str | None:
    if token is None or token == "":
        return None
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None
