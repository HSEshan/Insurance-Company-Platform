"""In-app notification list and read-state endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.common import Envelope, Meta, ok
from app.schemas.notification import NotificationRead, UnreadCount
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=Envelope[list[NotificationRead]])
async def list_notifications(
    unread_only: bool = Query(False),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    items, total = await notification_service.list_notifications(
        db,
        current_user,
        unread_only=unread_only,
        limit=per_page,
        offset=(page - 1) * per_page,
    )
    return ok(items, meta=Meta(page=page, per_page=per_page, total=total))


@router.get("/unread-count", response_model=Envelope[UnreadCount])
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    count = await notification_service.unread_count(db, current_user)
    return ok(UnreadCount(unread=count))


@router.post("/{notification_id}/read", response_model=Envelope[NotificationRead])
async def mark_read(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    notification = await notification_service.mark_read(
        db, notification_id, current_user
    )
    return ok(NotificationRead.model_validate(notification))


@router.post("/read-all", response_model=Envelope[UnreadCount])
async def mark_all_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    updated = await notification_service.mark_all_read(db, current_user)
    return ok(UnreadCount(unread=0 if updated >= 0 else 0))
