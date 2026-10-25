"""Contact verification and two-factor authentication endpoints.

Mounted under ``/auth`` next to the core auth routes. Everything except the
sign-in challenge (``/auth/mfa/verify`` and ``/auth/mfa/resend``, which take the
short-lived ``mfa_token`` from ``/auth/login``) requires a normal access token.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.redis_client import get_redis
from app.models.user import User
from app.schemas.auth import LoginResult
from app.schemas.common import Envelope, ok
from app.schemas.mfa import (
    CodeDispatch,
    EnableOtpMfaRequest,
    MfaResendRequest,
    MfaVerifyRequest,
    PasswordConfirmRequest,
    PhoneVerificationRequest,
    RecoveryCodesResult,
    SecurityStatus,
    TotpSetup,
    VerifyCodeRequest,
)
from app.services import auth_service, mfa_service, verification_service

router = APIRouter(prefix="/auth", tags=["auth: verification & 2FA"])


@router.get("/security", response_model=Envelope[SecurityStatus])
async def security_status(current_user: User = Depends(get_current_user)) -> dict:
    return ok(mfa_service.build_status(current_user))


# --------------------------------------------------------------------------- #
# Email / phone verification                                                   #
# --------------------------------------------------------------------------- #
@router.post("/verify/email/send", response_model=Envelope[CodeDispatch])
async def send_email_verification(
    current_user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> dict:
    return ok(await verification_service.send_email_code(redis, current_user))


@router.post("/verify/email/confirm", response_model=Envelope[SecurityStatus])
async def confirm_email_verification(
    payload: VerifyCodeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    user = await verification_service.confirm_email(db, redis, current_user, payload.code)
    return ok(mfa_service.build_status(user))


@router.post("/verify/phone/send", response_model=Envelope[CodeDispatch])
async def send_phone_verification(
    payload: PhoneVerificationRequest,
    current_user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> dict:
    return ok(
        await verification_service.send_phone_code(redis, current_user, payload.phone)
    )


@router.post("/verify/phone/confirm", response_model=Envelope[SecurityStatus])
async def confirm_phone_verification(
    payload: VerifyCodeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    user = await verification_service.confirm_phone(db, redis, current_user, payload.code)
    return ok(mfa_service.build_status(user))


# --------------------------------------------------------------------------- #
# 2FA management                                                               #
# --------------------------------------------------------------------------- #
@router.post("/mfa/totp/setup", response_model=Envelope[TotpSetup])
async def begin_totp_setup(
    payload: PasswordConfirmRequest,
    current_user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> dict:
    return ok(await mfa_service.begin_totp_setup(redis, current_user, payload.password))


@router.post("/mfa/totp/confirm", response_model=Envelope[RecoveryCodesResult])
async def confirm_totp_setup(
    payload: VerifyCodeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    return ok(await mfa_service.confirm_totp_setup(db, redis, current_user, payload.code))


@router.post("/mfa/enable", response_model=Envelope[RecoveryCodesResult])
async def enable_code_mfa(
    payload: EnableOtpMfaRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return ok(
        await mfa_service.enable_otp_method(
            db, current_user, payload.method, payload.password
        )
    )


@router.post("/mfa/disable", response_model=Envelope[SecurityStatus])
async def disable_mfa(
    payload: PasswordConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return ok(await mfa_service.disable(db, current_user, payload.password))


@router.post("/mfa/recovery-codes", response_model=Envelope[RecoveryCodesResult])
async def regenerate_recovery_codes(
    payload: PasswordConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return ok(
        await mfa_service.regenerate_recovery_codes(db, current_user, payload.password)
    )


# --------------------------------------------------------------------------- #
# Sign-in challenge (no access token yet)                                      #
# --------------------------------------------------------------------------- #
@router.post("/mfa/verify", response_model=Envelope[LoginResult])
async def verify_mfa_challenge(
    payload: MfaVerifyRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    return ok(
        await auth_service.complete_mfa_challenge(db, redis, payload.mfa_token, payload.code)
    )


@router.post("/mfa/resend", response_model=Envelope[CodeDispatch])
async def resend_mfa_code(
    payload: MfaResendRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    return ok(await auth_service.resend_mfa_code(db, redis, payload.mfa_token))
