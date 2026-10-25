"""Email and phone ownership verification via one-time codes.

Codes are delivered through ``app.services.delivery`` (simulated by default),
so swapping in a real email/SMS provider needs no changes here.
"""

from __future__ import annotations

from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, AuthError, ConflictError
from app.models.enums import MfaMethod
from app.models.user import User
from app.schemas.mfa import CodeDispatch
from app.services import audit_service, otp_service
from app.services.delivery import mask_phone


def normalize_phone(raw: str) -> str:
    """Normalize to E.164 (``+15551234567``). Bare 10-digit numbers are NANP."""
    stripped = raw.strip()
    digits = "".join(c for c in stripped if c.isdigit())
    if stripped.startswith("+") and 8 <= len(digits) <= 15:
        return f"+{digits}"
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    raise AppError(
        "Enter a valid phone number, e.g. (555) 123-4567 or +44 20 7946 0958.",
        code="INVALID_PHONE",
        status_code=422,
    )


def _same_phone(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    try:
        return normalize_phone(a) == normalize_phone(b)
    except AppError:
        return a == b


def apply_phone_change(user: User, new_phone: str | None) -> None:
    """Update ``user.phone`` from a profile/staff edit, resetting verification.

    Refuses while SMS is the user's second factor: otherwise an edit could
    silently redirect sign-in codes to a number nobody verified.
    """
    if new_phone == user.phone or _same_phone(new_phone, user.phone):
        return
    if user.mfa_method == MfaMethod.sms:
        raise ConflictError(
            "This phone number receives two-factor sign-in codes. Switch or turn off "
            "text-message 2FA before changing it.",
            code="PHONE_USED_FOR_MFA",
        )
    user.phone = new_phone
    user.phone_verified_at = None


# --------------------------------------------------------------------------- #
# Email                                                                        #
# --------------------------------------------------------------------------- #
async def send_email_code(redis: Redis, user: User) -> CodeDispatch:
    if user.email_verified_at is not None:
        raise ConflictError("Your email is already verified.", code="ALREADY_VERIFIED")
    return await otp_service.send_code(
        redis,
        purpose="verify_email",
        subject=str(user.id),
        channel="email",
        destination=user.email,
    )


async def confirm_email(db: AsyncSession, redis: Redis, user: User, code: str) -> User:
    destination = await otp_service.verify(
        redis, purpose="verify_email", subject=str(user.id), code=code
    )
    if destination.lower() != user.email.lower():
        raise AuthError(
            "This code was sent to a different address. Request a new one.",
            code="CODE_EXPIRED",
            status_code=400,
        )

    user.email_verified_at = datetime.now(UTC)
    await audit_service.record(
        db,
        action="user.email_verified",
        entity_type="user",
        entity_id=user.id,
        actor=user,
        new_value={"email": user.email},
    )
    await db.commit()
    await db.refresh(user)
    return user


# --------------------------------------------------------------------------- #
# Phone                                                                        #
# --------------------------------------------------------------------------- #
async def send_phone_code(redis: Redis, user: User, phone: str | None) -> CodeDispatch:
    raw = phone or user.phone
    if not raw:
        raise AppError(
            "Add a phone number to verify.", code="PHONE_REQUIRED", status_code=422
        )
    target = normalize_phone(raw)
    changing = not _same_phone(target, user.phone)

    if not changing and user.phone_verified_at is not None:
        raise ConflictError("This phone number is already verified.", code="ALREADY_VERIFIED")
    if changing and user.mfa_method == MfaMethod.sms:
        raise ConflictError(
            "Switch or turn off text-message 2FA before changing your number.",
            code="PHONE_USED_FOR_MFA",
        )

    return await otp_service.send_code(
        redis,
        purpose="verify_phone",
        subject=str(user.id),
        channel="sms",
        destination=target,
    )


async def confirm_phone(db: AsyncSession, redis: Redis, user: User, code: str) -> User:
    destination = await otp_service.verify(
        redis, purpose="verify_phone", subject=str(user.id), code=code
    )
    old_phone = user.phone
    user.phone = destination
    user.phone_verified_at = datetime.now(UTC)
    await audit_service.record(
        db,
        action="user.phone_verified",
        entity_type="user",
        entity_id=user.id,
        actor=user,
        old_value={"phone": mask_phone(old_phone)} if old_phone else None,
        new_value={"phone": mask_phone(destination)},
    )
    await db.commit()
    await db.refresh(user)
    return user
