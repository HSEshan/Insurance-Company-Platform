"""Two-factor authentication: TOTP enrollment, email/SMS codes, recovery codes.

Sign-in flow (see ``auth_service.authenticate``): a correct password for a user
with ``mfa_method`` set returns a short-lived ``mfa`` token instead of API
tokens; the client then calls ``POST /auth/mfa/verify`` with that token plus a
code, which ``verify_second_factor`` checks here.

Every change to a user's 2FA settings requires the current password.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import secrets
from datetime import UTC, datetime

import pyotp
import qrcode
import qrcode.image.svg
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError, AuthError, ConflictError, ForbiddenError
from app.core.security import decrypt_pii, encrypt_pii, verify_password
from app.models.enums import MfaMethod, NotificationType
from app.models.user import User
from app.schemas.mfa import CodeDispatch, RecoveryCodesResult, SecurityStatus, TotpSetup
from app.services import audit_service, notification_service, otp_service

# Shared demo logins (see ``scripts.seed`` / ``endpoints.public``). Turning on 2FA
# for these would lock every other visitor out, so it is blocked in demo mode.
SHARED_DEMO_EMAILS: frozenset[str] = frozenset(
    {
        "admin@insureco.com",
        "manager@insureco.com",
        "agent@insureco.com",
        "adjuster@insureco.com",
        "customer@insureco.com",
        "homeowner@insureco.com",
        "lifeholder@insureco.com",
    }
)

# No 0/o/1/l/i so codes survive being read aloud or written down.
_RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
_TOTP_PENDING_TTL = 10 * 60


def mfa_locked_reason(user: User) -> str | None:
    if settings.DEMO_MODE_ENABLED and user.email.lower() in SHARED_DEMO_EMAILS:
        return (
            "Two-factor authentication can't be turned on for shared demo accounts. "
            "Register your own account to try it."
        )
    return None


def available_methods(user: User) -> list[MfaMethod]:
    methods = [MfaMethod.totp]
    if user.email_verified_at is not None:
        methods.append(MfaMethod.email)
    if user.phone and user.phone_verified_at is not None:
        methods.append(MfaMethod.sms)
    return methods


def build_status(user: User) -> SecurityStatus:
    return SecurityStatus(
        email=user.email,
        email_verified=user.email_verified_at is not None,
        email_verified_at=user.email_verified_at,
        phone=user.phone,
        phone_verified=user.phone_verified_at is not None,
        phone_verified_at=user.phone_verified_at,
        mfa_enabled=user.mfa_method is not None,
        mfa_method=user.mfa_method,
        mfa_enabled_at=user.mfa_enabled_at,
        recovery_codes_remaining=len(user.mfa_recovery_codes or []),
        available_methods=available_methods(user),
        mfa_locked_reason=mfa_locked_reason(user),
    )


def _require_password(user: User, password: str) -> None:
    if not verify_password(password, user.hashed_password):
        # 403, not 401: the session is fine, and a 401 would trigger the SPA's
        # token-refresh-and-retry interceptor for nothing.
        raise AuthError("Password is incorrect.", code="INVALID_CREDENTIALS", status_code=403)


def _require_unlocked(user: User) -> None:
    reason = mfa_locked_reason(user)
    if reason:
        raise ForbiddenError(reason, code="DEMO_ACCOUNT_MFA_LOCKED")


# --------------------------------------------------------------------------- #
# Recovery codes                                                               #
# --------------------------------------------------------------------------- #
def _normalize_recovery_code(code: str) -> str:
    return "".join(c for c in code.lower() if c.isalnum())


def hash_recovery_code(code: str) -> str:
    # Codes carry ~49 bits of entropy each, so a fast hash is adequate here.
    return hashlib.sha256(_normalize_recovery_code(code).encode()).hexdigest()


def generate_recovery_codes(count: int | None = None) -> list[str]:
    count = count or settings.MFA_RECOVERY_CODE_COUNT
    codes = []
    for _ in range(count):
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(10))
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes


def looks_like_recovery_code(code: str) -> bool:
    return any(c.isalpha() for c in code) or "-" in code


def consume_recovery_code(user: User, code: str) -> bool:
    """Remove a matching recovery code from ``user``. Returns True if one matched."""
    target = hash_recovery_code(code)
    remaining = list(user.mfa_recovery_codes or [])
    for stored in remaining:
        if hmac.compare_digest(stored, target):
            remaining.remove(stored)
            # Reassign (not mutate) so SQLAlchemy notices the JSONB change.
            user.mfa_recovery_codes = remaining
            return True
    return False


def _issue_recovery_codes(user: User) -> list[str]:
    codes = generate_recovery_codes()
    user.mfa_recovery_codes = [hash_recovery_code(c) for c in codes]
    return codes


# --------------------------------------------------------------------------- #
# TOTP                                                                         #
# --------------------------------------------------------------------------- #
def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=settings.TOTP_ISSUER)


def qr_code_data_uri(data: str) -> str:
    """Render ``data`` as an SVG QR code (white background) and return a data URI."""
    image = qrcode.make(data, image_factory=qrcode.image.svg.SvgPathFillImage, box_size=10)
    buffer = io.BytesIO()
    image.save(buffer)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def match_totp(secret: str, code: str, at: datetime | None = None) -> int | None:
    """Return the matching time-step counter (±1 step of drift) or None."""
    code = code.strip().replace(" ", "")
    if not code.isdigit():
        return None
    totp = pyotp.TOTP(secret)
    now = at or datetime.now(UTC)
    current = totp.timecode(now)
    for counter in (current, current - 1, current + 1):
        if hmac.compare_digest(totp.generate_otp(counter), code):
            return counter
    return None


async def _accept_totp(redis: Redis, user: User, secret: str, code: str) -> bool:
    """Verify a TOTP code and reject replays of an already-used time step."""
    counter = match_totp(secret, code)
    if counter is None:
        return False
    key = f"mfa:totp_last:{user.id}"
    last = await redis.get(key)
    if last is not None and int(last) >= counter:
        return False
    await redis.set(key, str(counter), ex=5 * 60)
    return True


def _pending_key(user: User) -> str:
    return f"mfa:totp_pending:{user.id}"


async def begin_totp_setup(redis: Redis, user: User, password: str) -> TotpSetup:
    _require_unlocked(user)
    _require_password(user, password)
    secret = pyotp.random_base32()
    # Encrypted at rest even in Redis; it only becomes active once confirmed.
    await redis.set(_pending_key(user), encrypt_pii(secret) or "", ex=_TOTP_PENDING_TTL)
    uri = provisioning_uri(secret, user.email)
    return TotpSetup(
        secret=secret,
        otpauth_uri=uri,
        qr_code_data_uri=qr_code_data_uri(uri),
        expires_in_seconds=_TOTP_PENDING_TTL,
    )


async def confirm_totp_setup(
    db: AsyncSession, redis: Redis, user: User, code: str
) -> RecoveryCodesResult:
    _require_unlocked(user)
    secret = decrypt_pii(await redis.get(_pending_key(user)))
    if not secret:
        raise AppError(
            "Authenticator setup expired. Start again.",
            code="TOTP_SETUP_EXPIRED",
            status_code=400,
        )
    if not await _accept_totp(redis, user, secret, code):
        raise AuthError(
            "That code didn't match. Check your device's clock and try the current code.",
            code="INVALID_CODE",
            status_code=400,
        )

    await redis.delete(_pending_key(user))
    user.totp_secret_encrypted = encrypt_pii(secret)
    return await _enable(db, user, MfaMethod.totp)


async def enable_otp_method(
    db: AsyncSession, user: User, method: MfaMethod, password: str
) -> RecoveryCodesResult:
    _require_unlocked(user)
    _require_password(user, password)
    if method not in available_methods(user) or method == MfaMethod.totp:
        channel = "email address" if method == MfaMethod.email else "phone number"
        raise ConflictError(
            f"Verify your {channel} before using it for two-factor authentication.",
            code="CHANNEL_NOT_VERIFIED",
        )
    user.totp_secret_encrypted = None
    return await _enable(db, user, method)


async def _enable(db: AsyncSession, user: User, method: MfaMethod) -> RecoveryCodesResult:
    previous = user.mfa_method
    user.mfa_method = method
    user.mfa_enabled_at = datetime.now(UTC)
    codes = _issue_recovery_codes(user)
    await audit_service.record(
        db,
        action="auth.mfa_enabled" if previous is None else "auth.mfa_method_changed",
        entity_type="user",
        entity_id=user.id,
        actor=user,
        old_value={"mfa_method": previous.value} if previous else None,
        new_value={"mfa_method": method.value},
    )
    notification = await notification_service.emit(
        db,
        user_id=user.id,
        notification_type=NotificationType.general,
        title="Two-factor authentication is on",
        body=f"Sign-ins now require a code from your {_method_label(method)}. "
        "If this wasn't you, change your password and contact support.",
        related_entity_type="user",
        related_entity_id=user.id,
    )
    await db.commit()
    notification_service.queue_email(notification.id)
    await db.refresh(user)
    return RecoveryCodesResult(recovery_codes=codes, status=build_status(user))


async def disable(db: AsyncSession, user: User, password: str) -> SecurityStatus:
    _require_password(user, password)
    if user.mfa_method is None:
        raise ConflictError(
            "Two-factor authentication is already off.", code="MFA_NOT_ENABLED"
        )

    previous = user.mfa_method
    user.mfa_method = None
    user.mfa_enabled_at = None
    user.totp_secret_encrypted = None
    user.mfa_recovery_codes = None
    await audit_service.record(
        db,
        action="auth.mfa_disabled",
        entity_type="user",
        entity_id=user.id,
        actor=user,
        old_value={"mfa_method": previous.value},
    )
    notification = await notification_service.emit(
        db,
        user_id=user.id,
        notification_type=NotificationType.general,
        title="Two-factor authentication is off",
        body="Your account now signs in with a password only. If this wasn't you, "
        "change your password and contact support.",
        related_entity_type="user",
        related_entity_id=user.id,
    )
    await db.commit()
    notification_service.queue_email(notification.id)
    await db.refresh(user)
    return build_status(user)


async def regenerate_recovery_codes(
    db: AsyncSession, user: User, password: str
) -> RecoveryCodesResult:
    _require_password(user, password)
    if user.mfa_method is None:
        raise ConflictError(
            "Turn on two-factor authentication first.", code="MFA_NOT_ENABLED"
        )
    codes = _issue_recovery_codes(user)
    await audit_service.record(
        db,
        action="auth.mfa_recovery_codes_regenerated",
        entity_type="user",
        entity_id=user.id,
        actor=user,
        new_value={"count": len(codes)},
    )
    await db.commit()
    await db.refresh(user)
    return RecoveryCodesResult(recovery_codes=codes, status=build_status(user))


def _method_label(method: MfaMethod) -> str:
    return {
        MfaMethod.totp: "authenticator app",
        MfaMethod.email: "email",
        MfaMethod.sms: "phone (text message)",
    }[method]


# --------------------------------------------------------------------------- #
# Sign-in second factor                                                        #
# --------------------------------------------------------------------------- #
def _login_subject(user: User, method: MfaMethod) -> str:
    # Per channel, so switching email <-> SMS never leaves a live code (or a
    # resend cooldown) on the channel the user is no longer reading.
    return f"{user.id}:{method.value}"


async def send_login_code(redis: Redis, user: User) -> CodeDispatch | None:
    """Send an email/SMS sign-in code. Returns None for TOTP (nothing to send)."""
    if user.mfa_method == MfaMethod.email:
        return await otp_service.send_code(
            redis,
            purpose="login",
            subject=_login_subject(user, MfaMethod.email),
            channel="email",
            destination=user.email,
        )
    if user.mfa_method == MfaMethod.sms and user.phone:
        return await otp_service.send_code(
            redis,
            purpose="login",
            subject=_login_subject(user, MfaMethod.sms),
            channel="sms",
            destination=user.phone,
        )
    return None


async def verify_second_factor(redis: Redis, user: User, code: str) -> str:
    """Check ``code`` for the user's method (or a recovery code).

    Returns the factor that matched (``totp``/``email``/``sms``/``recovery``);
    raises ``AuthError`` otherwise. A consumed recovery code is mutated on the
    user and must be committed by the caller.
    """
    code = code.strip()
    if looks_like_recovery_code(code):
        if consume_recovery_code(user, code):
            return "recovery"
        raise AuthError(
            "That recovery code is not valid.", code="INVALID_CODE", status_code=400
        )

    if user.mfa_method == MfaMethod.totp:
        secret = decrypt_pii(user.totp_secret_encrypted)
        if secret and await _accept_totp(redis, user, secret, code):
            return MfaMethod.totp.value
        raise AuthError("That code is incorrect.", code="INVALID_CODE", status_code=400)

    if user.mfa_method in (MfaMethod.email, MfaMethod.sms):
        await otp_service.verify(
            redis, purpose="login", subject=_login_subject(user, user.mfa_method), code=code
        )
        return user.mfa_method.value

    raise AuthError("Two-factor authentication is not enabled.", code="MFA_NOT_ENABLED")
