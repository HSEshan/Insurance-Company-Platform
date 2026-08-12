"""Live-chat widget API (demo virtual assistant + simulated handoff)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_optional_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.chat import (
    ChatMessageCreate,
    ChatMessageRead,
    ChatMessageReply,
    ChatSessionCreate,
    ChatSessionRead,
)
from app.schemas.common import Envelope, ok
from app.services import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


def _session_read(session: object) -> ChatSessionRead:
    return ChatSessionRead.model_validate(session)


@router.post("/sessions", response_model=Envelope[ChatSessionRead])
async def create_session(
    payload: ChatSessionCreate,
    db: AsyncSession = Depends(get_db),
    actor: User | None = Depends(get_optional_user),
) -> dict:
    session = await chat_service.start_session(
        db, context=payload.context, actor=actor
    )
    return ok(_session_read(session))


@router.get("/sessions/{session_id}", response_model=Envelope[ChatSessionRead])
async def read_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User | None = Depends(get_optional_user),
) -> dict:
    session = await chat_service.get_session(db, session_id, actor)
    return ok(_session_read(session))


@router.post(
    "/sessions/{session_id}/messages",
    response_model=Envelope[ChatMessageReply],
)
async def post_message(
    session_id: uuid.UUID,
    payload: ChatMessageCreate,
    db: AsyncSession = Depends(get_db),
    actor: User | None = Depends(get_optional_user),
) -> dict:
    session, user_msg, reply = await chat_service.send_message(
        db, session_id, payload.body, actor
    )
    return ok(
        ChatMessageReply(
            session=_session_read(session),
            user_message=ChatMessageRead.model_validate(user_msg),
            reply=ChatMessageRead.model_validate(reply),
        )
    )


@router.post(
    "/sessions/{session_id}/escalate",
    response_model=Envelope[ChatSessionRead],
)
async def escalate_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User | None = Depends(get_optional_user),
) -> dict:
    session = await chat_service.escalate(db, session_id, actor)
    return ok(_session_read(session))
