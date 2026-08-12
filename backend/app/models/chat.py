"""Live-chat session and message models (demo virtual assistant)."""

from __future__ import annotations

import uuid

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import ChatMessageRole, ChatSessionMode


class ChatSession(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "chat_sessions"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    mode: Mapped[ChatSessionMode] = mapped_column(
        SQLEnum(ChatSessionMode, name="chat_session_mode"),
        nullable=False,
        default=ChatSessionMode.ai,
    )
    agent_name: Mapped[str | None] = mapped_column(String(120))
    context: Mapped[str | None] = mapped_column(String(40))

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )


class ChatMessage(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "chat_messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[ChatMessageRole] = mapped_column(
        SQLEnum(ChatMessageRole, name="chat_message_role"),
        nullable=False,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # "ai" | "human" | None for user/system rows
    sender_kind: Mapped[str | None] = mapped_column(String(20))

    session: Mapped[ChatSession] = relationship(back_populates="messages")
