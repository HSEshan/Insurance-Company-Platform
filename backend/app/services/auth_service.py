"""Authentication business logic: registration, login, token issuance."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import jwt
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AuthError, ConflictError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.customer import Customer
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.auth import AuthResult, RegisterRequest, TokenPair
from app.schemas.user import ChangePasswordRequest, UserRead
from app.services import audit_service


def _lockout_key(email: str) -> str:
    return f"login:attempts:{email.lower()}"


def _build_token_pair(user: User) -> TokenPair:
    claims = {"role": user.role.value, "email": user.email}
    return TokenPair(
        access_token=create_access_token(str(user.id), extra_claims=claims),
        refresh_token=create_refresh_token(str(user.id)),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


async def register_customer(db: AsyncSession, payload: RegisterRequest) -> AuthResult:
    existing = await db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise ConflictError(
            "An account with this email already exists.", code="EMAIL_TAKEN"
        )

    user = User(
        email=str(payload.email),
        hashed_password=hash_password(payload.password),
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone=payload.phone,
        role=UserRole.customer,
    )
    user.customer = Customer(date_of_birth=payload.date_of_birth)
    db.add(user)
    await db.flush()
    await audit_service.record(
        db,
        action="auth.register",
        entity_type="user",
        entity_id=user.id,
        actor=user,
        new_value={"email": user.email, "role": user.role.value},
    )
    await db.commit()
    await db.refresh(user)

    return AuthResult(user=UserRead.model_validate(user), tokens=_build_token_pair(user))


async def authenticate(
    db: AsyncSession, redis: Redis, email: str, password: str
) -> AuthResult:
    key = _lockout_key(email)
    attempts = await redis.get(key)
    if attempts is not None and int(attempts) >= settings.MAX_LOGIN_ATTEMPTS:
        raise AuthError(
            "Account temporarily locked due to too many failed attempts. "
            "Please try again later.",
            code="ACCOUNT_LOCKED",
            status_code=429,
        )

    user = await db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(password, user.hashed_password):
        new_count = await redis.incr(key)
        if new_count == 1:
            await redis.expire(key, settings.LOGIN_LOCKOUT_MINUTES * 60)
        # Commit independently: this path raises and would otherwise lose the row.
        await audit_service.record(
            db,
            action="auth.login_failed",
            entity_type="user",
            entity_id=user.id if user else audit_service.ANONYMOUS_ENTITY_ID,
            actor_role=user.role if user else None,
            new_value={"email": email.lower()},
            commit=True,
        )
        raise AuthError("Invalid email or password.", code="INVALID_CREDENTIALS")

    if not user.is_active:
        await audit_service.record(
            db,
            action="auth.login_failed",
            entity_type="user",
            entity_id=user.id,
            actor=user,
            new_value={"email": email.lower(), "reason": "deactivated"},
            commit=True,
        )
        raise AuthError("Account is deactivated.", code="ACCOUNT_DEACTIVATED", status_code=403)

    await redis.delete(key)
    user.last_login = datetime.now(UTC)
    await audit_service.record(
        db,
        action="auth.login_success",
        entity_type="user",
        entity_id=user.id,
        actor=user,
        new_value={"email": user.email},
    )
    await db.commit()
    await db.refresh(user)

    return AuthResult(user=UserRead.model_validate(user), tokens=_build_token_pair(user))


async def change_password(
    db: AsyncSession, user: User, payload: ChangePasswordRequest
) -> User:
    if not verify_password(payload.current_password, user.hashed_password):
        raise AuthError("Current password is incorrect.", code="INVALID_CREDENTIALS")
    if payload.current_password == payload.new_password:
        raise AuthError(
            "New password must be different from the current password.",
            code="PASSWORD_UNCHANGED",
            status_code=422,
        )

    user.hashed_password = hash_password(payload.new_password)
    user.must_reset_password = False
    await audit_service.record(
        db,
        action="auth.password_changed",
        entity_type="user",
        entity_id=user.id,
        actor=user,
        new_value={"must_reset_password": False},
    )
    await db.commit()
    await db.refresh(user)
    return user


async def refresh_tokens(db: AsyncSession, refresh_token: str) -> TokenPair:
    try:
        payload = decode_token(refresh_token)
    except jwt.PyJWTError:
        raise AuthError(
            "Invalid or expired refresh token.", code="INVALID_REFRESH"
        ) from None

    if payload.get("type") != "refresh":
        raise AuthError("Invalid token type.", code="INVALID_REFRESH")

    subject = payload.get("sub")
    try:
        user_id = uuid.UUID(str(subject))
    except (ValueError, TypeError):
        raise AuthError("Invalid refresh token.", code="INVALID_REFRESH") from None

    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None or not user.is_active:
        raise AuthError("User not found or inactive.", code="INVALID_REFRESH")

    return _build_token_pair(user)
