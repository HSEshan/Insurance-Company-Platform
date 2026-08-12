"""Chat session / message schemas for the demo live-chat widget."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ChatMessageRole, ChatSessionMode


class ChatSessionCreate(BaseModel):
    context: Literal["landing", "customer_dashboard"] = "landing"


class ChatMessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class ChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: ChatMessageRole
    body: str
    sender_kind: str | None = None
    created_at: datetime


class ChatSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    mode: ChatSessionMode
    agent_name: str | None = None
    context: str | None = None
    user_id: uuid.UUID | None = None
    created_at: datetime
    messages: list[ChatMessageRead] = []


class ChatMessageReply(BaseModel):
    """Response after sending a message (user row + simulated reply)."""

    session: ChatSessionRead
    user_message: ChatMessageRead
    reply: ChatMessageRead
