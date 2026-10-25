"""Authentication business logic: registration, login, token issuance."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import jwt
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError, AuthError, ConflictError
from app.core.security import (
    create_access_token,
    create_mfa_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.customer import Customer
from app.models.enums import MfaMethod, UserRole
from app.models.user import User
from app.schemas.auth import AuthResult, LoginResult, RegisterRequest, TokenPair
from app.schemas.mfa import CodeDispatch, MfaChallenge
from app.schemas.user import ChangePasswordRequest, UserRead
from app.services import audit_service, mfa_service
from app.services.delivery import mask_email, mask_phone


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


async def _ensure_not_locked(redis: Redis, email: str) -> None:
    attempts = await redis.get(_lockout_key(email))
    if attempts is not None and int(attempts) >= settings.MAX_LOGIN_ATTEMPTS:
        raise AuthError(
            "Account temporarily locked due to too many failed attempts. "
            "Please try again later.",
            code="ACCOUNT_LOCKED",
            status_code=429,
        )


async def _count_failure(redis: Redis, email: str) -> None:
    key = _lockout_key(email)
    new_count = await redis.incr(key)
    if new_count == 1:
        await redis.expire(key, settings.LOGIN_LOCKOUT_MINUTES * 60)


async def authenticate(
    db: AsyncSession, redis: Redis, email: str, password: str
) -> LoginResult:
    await _ensure_not_locked(redis, email)

    user = await db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(password, user.hashed_password):
        await _count_failure(redis, email)
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

    if user.mfa_method is not None:
        # Password is right; the lockout counter is cleared only once the second
        # factor passes too.
        return LoginResult(mfa_required=True, challenge=await _start_challenge(redis, user))

    await redis.delete(_lockout_key(email))
    return await _finish_login(db, user, factor=None)


async def _finish_login(db: AsyncSession, user: User, *, factor: str | None) -> LoginResult:
    user.last_login = datetime.now(UTC)
    detail: dict[str, str] = {"email": user.email}
    if factor:
        detail["mfa"] = factor
    await audit_service.record(
        db,
        action="auth.login_success",
        entity_type="user",
        entity_id=user.id,
        actor=user,
        new_value=detail,
    )
    await db.commit()
    await db.refresh(user)
    return LoginResult(user=UserRead.model_validate(user), tokens=_build_token_pair(user))


# --------------------------------------------------------------------------- #
# Two-factor sign-in challenge                                                 #
# --------------------------------------------------------------------------- #
def _challenge_destination(user: User) -> str | None:
    if user.mfa_method == MfaMethod.email:
        return mask_email(user.email)
    if user.mfa_method == MfaMethod.sms and user.phone:
        return mask_phone(user.phone)
    return None


async def _send_login_code(redis: Redis, user: User) -> CodeDispatch | None:
    try:
        return await mfa_service.send_login_code(redis, user)
    except AppError as exc:
        # A code sent moments ago is still valid; don't fail the sign-in over it.
        if exc.code == "CODE_RECENTLY_SENT":
            return None
        raise


async def _start_challenge(redis: Redis, user: User) -> MfaChallenge:
    assert user.mfa_method is not None
    return MfaChallenge(
        mfa_token=create_mfa_token(str(user.id), {"method": user.mfa_method.value}),
        method=user.mfa_method,
        destination=_challenge_destination(user),
        expires_in_seconds=settings.MFA_CHALLENGE_TTL_MINUTES * 60,
        dispatch=await _send_login_code(redis, user),
    )


def _used_key(jti: str) -> str:
    return f"mfa:challenge:{jti}:used"


async def _user_from_mfa_token(
    db: AsyncSession, redis: Redis, token: str
) -> tuple[User, str]:
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        raise AuthError(
            "Your sign-in session expired. Please sign in again.",
            code="MFA_TOKEN_INVALID",
        ) from None
    jti = str(payload.get("jti") or "")
    if payload.get("type") != "mfa" or not jti:
        raise AuthError("Invalid sign-in session.", code="MFA_TOKEN_INVALID")
    if await redis.exists(_used_key(jti)):
        raise AuthError("This sign-in session was already used.", code="MFA_TOKEN_INVALID")

    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except (ValueError, TypeError):
        raise AuthError("Invalid sign-in session.", code="MFA_TOKEN_INVALID") from None
    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None or not user.is_active or user.mfa_method is None:
        raise AuthError("Invalid sign-in session.", code="MFA_TOKEN_INVALID")
    return user, jti


async def complete_mfa_challenge(
    db: AsyncSession, redis: Redis, mfa_token: str, code: str
) -> LoginResult:
    user, jti = await _user_from_mfa_token(db, redis, mfa_token)
    await _ensure_not_locked(redis, user.email)

    attempts_key = f"mfa:challenge:{jti}:attempts"
    attempts = await redis.incr(attempts_key)
    if attempts == 1:
        await redis.expire(attempts_key, settings.MFA_CHALLENGE_TTL_MINUTES * 60)
    if attempts > settings.OTP_MAX_ATTEMPTS:
        raise AuthError(
            "Too many incorrect codes. Please sign in again.",
            code="MFA_ATTEMPTS_EXCEEDED",
            status_code=429,
        )

    try:
        factor = await mfa_service.verify_second_factor(redis, user, code)
    except AuthError:
        await _count_failure(redis, user.email)
        await audit_service.record(
            db,
            action="auth.mfa_failed",
            entity_type="user",
            entity_id=user.id,
            actor=user,
            new_value={"method": user.mfa_method.value if user.mfa_method else None},
            commit=True,
        )
        raise

    # Single-use: the same token can't mint a second session within its TTL.
    await redis.set(_used_key(jti), "1", ex=settings.MFA_CHALLENGE_TTL_MINUTES * 60)
    await redis.delete(_lockout_key(user.email), attempts_key)
    if factor == "recovery":
        await audit_service.record(
            db,
            action="auth.mfa_recovery_code_used",
            entity_type="user",
            entity_id=user.id,
            actor=user,
            new_value={"remaining": len(user.mfa_recovery_codes or [])},
        )
    return await _finish_login(db, user, factor=factor)


async def resend_mfa_code(db: AsyncSession, redis: Redis, mfa_token: str) -> CodeDispatch:
    user, _ = await _user_from_mfa_token(db, redis, mfa_token)
    dispatch = await mfa_service.send_login_code(redis, user)
    if dispatch is None:
        raise AppError(
            "Open your authenticator app for the current code.",
            code="NOTHING_TO_RESEND",
            status_code=400,
        )
    return dispatch


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
