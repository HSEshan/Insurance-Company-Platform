"""Super-Admin staff / employee management endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SUPER_ADMIN_ONLY, require_roles
from app.core.database import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.common import Envelope, Meta, ok
from app.schemas.staff import (
    OpenWorkSummary,
    StaffCreate,
    StaffCreateResult,
    StaffDeactivate,
    StaffUpdate,
)
from app.schemas.user import UserRead
from app.services import staff_service

router = APIRouter(prefix="/admin/users", tags=["admin"])


@router.get("", response_model=Envelope[list[UserRead]])
async def list_staff(
    role: UserRole | None = Query(None),
    include_inactive: bool = Query(True),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    _: User = Depends(require_roles(*SUPER_ADMIN_ONLY)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    users, total = await staff_service.list_staff(
        db,
        role=role,
        include_inactive=include_inactive,
        page=page,
        per_page=per_page,
    )
    return ok(
        [UserRead.model_validate(u) for u in users],
        meta=Meta(page=page, per_page=per_page, total=total),
    )


@router.post(
    "",
    response_model=Envelope[StaffCreateResult],
    status_code=status.HTTP_201_CREATED,
)
async def create_staff(
    payload: StaffCreate,
    current_user: User = Depends(require_roles(*SUPER_ADMIN_ONLY)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await staff_service.create_staff(db, current_user, payload)
    return ok(result)


@router.get("/{user_id}", response_model=Envelope[UserRead])
async def get_staff(
    user_id: uuid.UUID,
    _: User = Depends(require_roles(*SUPER_ADMIN_ONLY)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await staff_service.get_staff_user(db, user_id)
    return ok(UserRead.model_validate(user))


@router.get("/{user_id}/open-work", response_model=Envelope[OpenWorkSummary])
async def get_open_work(
    user_id: uuid.UUID,
    _: User = Depends(require_roles(*SUPER_ADMIN_ONLY)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await staff_service.get_staff_user(db, user_id)
    return ok(await staff_service.open_work(db, user))


@router.patch("/{user_id}", response_model=Envelope[UserRead])
async def update_staff(
    user_id: uuid.UUID,
    payload: StaffUpdate,
    current_user: User = Depends(require_roles(*SUPER_ADMIN_ONLY)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await staff_service.update_staff(db, current_user, user_id, payload)
    return ok(UserRead.model_validate(user))


@router.post("/{user_id}/deactivate", response_model=Envelope[UserRead])
async def deactivate_staff(
    user_id: uuid.UUID,
    payload: StaffDeactivate,
    current_user: User = Depends(require_roles(*SUPER_ADMIN_ONLY)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await staff_service.deactivate_staff(db, current_user, user_id, payload)
    return ok(UserRead.model_validate(user))


@router.post("/{user_id}/reactivate", response_model=Envelope[UserRead])
async def reactivate_staff(
    user_id: uuid.UUID,
    current_user: User = Depends(require_roles(*SUPER_ADMIN_ONLY)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await staff_service.reactivate_staff(db, current_user, user_id)
    return ok(UserRead.model_validate(user))


@router.post("/{user_id}/reset-password", response_model=Envelope[StaffCreateResult])
async def reset_staff_password(
    user_id: uuid.UUID,
    current_user: User = Depends(require_roles(*SUPER_ADMIN_ONLY)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await staff_service.reset_temp_password(db, current_user, user_id)
    return ok(result)
