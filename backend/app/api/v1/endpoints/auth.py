"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.redis_client import get_redis
from app.models.user import User
from app.schemas.auth import (
    AuthResult,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
)
from app.schemas.common import Envelope, ok
from app.schemas.user import ChangePasswordRequest, UserRead
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=Envelope[AuthResult],
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    result = await auth_service.register_customer(db, payload)
    return ok(result)


@router.post("/login", response_model=Envelope[AuthResult])
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    result = await auth_service.authenticate(
        db, redis, payload.email, payload.password
    )
    return ok(result)


@router.post("/refresh", response_model=Envelope[TokenPair])
async def refresh(
    payload: RefreshRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    tokens = await auth_service.refresh_tokens(db, payload.refresh_token)
    return ok(tokens)


@router.post("/logout", response_model=Envelope[dict])
async def logout(_: User = Depends(get_current_user)) -> dict:
    # Tokens are stateless; the client discards them. A Redis blocklist can be
    # layered in here for true server-side revocation in a later phase.
    return ok({"message": "Logged out successfully."})


@router.get("/me", response_model=Envelope[UserRead])
async def me(current_user: User = Depends(get_current_user)) -> dict:
    return ok(UserRead.model_validate(current_user))


@router.post("/change-password", response_model=Envelope[UserRead])
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await auth_service.change_password(db, current_user, payload)
    return ok(UserRead.model_validate(user))
