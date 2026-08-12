"""Notification request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import NotificationType


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: NotificationType
    title: str | None = None
    body: str | None = None
    is_read: bool
    related_entity_type: str | None = None
    related_entity_id: uuid.UUID | None = None
    sent_via_email: bool
    created_at: datetime


class UnreadCount(BaseModel):
    unread: int
