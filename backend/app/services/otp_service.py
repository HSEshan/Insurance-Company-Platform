"""Short-lived numeric one-time codes stored in Redis.

Used for email/phone verification and for email/SMS second factors at sign-in.
Only an HMAC of the code is stored; each code allows ``OTP_MAX_ATTEMPTS``
guesses, expires after ``OTP_TTL_MINUTES``, and re-sends are throttled.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from typing import Literal

from redis.asyncio import Redis

from app.core.config import settings
from app.core.exceptions import AppError, AuthError
from app.schemas.mfa import CodeDispatch
from app.services.delivery import (
    DeliveryReceipt,
    get_email_sender,
    get_sms_sender,
    mask_email,
    mask_phone,
)

Purpose = Literal["verify_email", "verify_phone", "login"]


def _key(purpose: Purpose, subject: str) -> str:
    return f"otp:{purpose}:{subject}"


def generate_code(length: int | None = None) -> str:
    length = length or settings.OTP_LENGTH
    return f"{secrets.randbelow(10**length):0{length}d}"


def hash_code(purpose: Purpose, subject: str, code: str) -> str:
    message = f"{purpose}:{subject}:{code}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()


async def issue(redis: Redis, *, purpose: Purpose, subject: str, destination: str) -> str:
    """Create (or replace) the active code for ``purpose``/``subject``."""
    cooldown_key = f"{_key(purpose, subject)}:cooldown"
    cooldown = settings.OTP_RESEND_COOLDOWN_SECONDS
    if cooldown > 0 and not await redis.set(cooldown_key, "1", ex=cooldown, nx=True):
        retry_after = max(await redis.ttl(cooldown_key), 1)
        raise AppError(
            f"Please wait {retry_after} seconds before requesting another code.",
            code="CODE_RECENTLY_SENT",
            status_code=429,
            details={"retry_after_seconds": retry_after},
        )

    code = generate_code()
    ttl = settings.OTP_TTL_MINUTES * 60
    record = {"hash": hash_code(purpose, subject, code), "destination": destination}
    await redis.set(_key(purpose, subject), json.dumps(record), ex=ttl)
    await redis.delete(f"{_key(purpose, subject)}:attempts")
    return code


async def verify(redis: Redis, *, purpose: Purpose, subject: str, code: str) -> str:
    """Consume a valid code and return the destination it was sent to."""
    key = _key(purpose, subject)
    raw = await redis.get(key)
    if raw is None:
        raise AuthError(
            "This code has expired. Request a new one.",
            code="CODE_EXPIRED",
            status_code=400,
        )
    record = json.loads(raw)

    attempts_key = f"{key}:attempts"
    attempts = await redis.incr(attempts_key)
    if attempts == 1:
        await redis.expire(attempts_key, settings.OTP_TTL_MINUTES * 60)
    if attempts > settings.OTP_MAX_ATTEMPTS:
        await redis.delete(key, attempts_key)
        raise AuthError(
            "Too many incorrect attempts. Request a new code.",
            code="CODE_ATTEMPTS_EXCEEDED",
            status_code=429,
        )

    expected = hash_code(purpose, subject, code.strip())
    if not hmac.compare_digest(expected, record["hash"]):
        raise AuthError("That code is incorrect.", code="INVALID_CODE", status_code=400)

    await redis.delete(key, attempts_key)
    return str(record["destination"])


def _message(purpose: Purpose, code: str) -> tuple[str, str]:
    if purpose == "login":
        title = f"{settings.APP_NAME}: your sign-in code"
        lead = "Use this code to finish signing in"
    else:
        title = f"{settings.APP_NAME}: verify your contact details"
        lead = "Use this code to verify your contact details"
    body = (
        f"{lead}: {code}\n\n"
        f"It expires in {settings.OTP_TTL_MINUTES} minutes. If you did not request "
        "it, you can ignore this message."
    )
    return title, body


def _to_dispatch(receipt: DeliveryReceipt, code: str) -> CodeDispatch:
    masked = (
        mask_email(receipt.destination)
        if receipt.channel == "email"
        else mask_phone(receipt.destination)
    )
    expose = receipt.simulated and settings.OTP_EXPOSE_SIMULATED_CODES
    return CodeDispatch(
        channel=receipt.channel,
        destination=masked,
        expires_in_seconds=settings.OTP_TTL_MINUTES * 60,
        resend_after_seconds=settings.OTP_RESEND_COOLDOWN_SECONDS,
        simulated=receipt.simulated,
        simulated_code=code if expose else None,
    )


async def send_code(
    redis: Redis,
    *,
    purpose: Purpose,
    subject: str,
    channel: Literal["email", "sms"],
    destination: str,
) -> CodeDispatch:
    """Issue a code and deliver it over ``channel``."""
    code = await issue(redis, purpose=purpose, subject=subject, destination=destination)
    title, body = _message(purpose, code)
    if channel == "email":
        receipt = await get_email_sender().send(to=destination, subject=title, body=body)
    else:
        receipt = await get_sms_sender().send(to=destination, body=f"{title}. {body}")

    if not receipt.delivered:
        # Let the user retry immediately rather than waiting out the cooldown.
        key = _key(purpose, subject)
        await redis.delete(key, f"{key}:cooldown")
        raise AppError(
            "We couldn't deliver the code right now. Please try again shortly.",
            code="DELIVERY_FAILED",
            status_code=503,
        )
    return _to_dispatch(receipt, code)
