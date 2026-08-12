"""Demo live-chat: FAQ assistant with simulated human handoff.

All replies are scripted — no external LLM. Pure helpers at the top are
unit-tested without a database.
"""

from __future__ import annotations

import re
import uuid
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.exceptions import AppError, ForbiddenError, NotFoundError
from app.models.chat import ChatMessage, ChatSession
from app.models.enums import ChatMessageRole, ChatSessionMode, UserRole
from app.models.user import User

HUMAN_AGENT_NAME = "Alex Rivera"
HUMAN_AGENT_TITLE = "Member Services"
HUMAN_AGENT_DISPLAY = f"{HUMAN_AGENT_NAME}, {HUMAN_AGENT_TITLE}"

Context = Literal["landing", "customer_dashboard"]

_ESCALATION_PATTERNS = (
    r"\btalk to (a |an )?(human|person|someone|agent|representative|rep)\b",
    r"\bspeak (to|with) (a |an )?(human|person|someone|agent|representative|rep)\b",
    r"\breal (person|human|agent)\b",
    r"\blive agent\b",
    r"\bhuman (please|agent|help)\b",
    r"\bconnect me\b",
    r"\bescalat",
    r"\brepresentative\b",
    r"\bcustomer service\b",
    r"\bmember services\b",
)

_RETURN_TO_AI_PATTERNS = (
    r"\b(back to|return to) (the )?(ai|assistant|bot|virtual)\b",
    r"\bvirtual assistant\b",
    r"\btalk to (the )?ai\b",
)

# (intent_key, keyword regexes) — first match wins.
_INTENT_MAP: list[tuple[str, tuple[str, ...]]] = [
    (
        "greeting",
        (r"\b(hi|hello|hey|good morning|good afternoon)\b",),
    ),
    (
        "quote",
        (
            r"\bquote\b",
            r"\bget (a |an )?quote\b",
            r"\bpricing\b",
            r"\bpremium\b",
            r"\bhow much\b",
        ),
    ),
    (
        "coverage",
        (
            r"\bcoverage\b",
            r"\bauto\b",
            r"\bhome\b",
            r"\blife\b",
            r"\bproduct\b",
            r"\blines? of business\b",
            r"\bwhat do you (offer|insure)\b",
        ),
    ),
    (
        "claim",
        (
            r"\bclaim\b",
            r"\bfile (a )?claim\b",
            r"\bloss\b",
            r"\baccident\b",
            r"\badjudicat",
        ),
    ),
    (
        "billing",
        (
            r"\bbill(ing)?\b",
            r"\bpayment\b",
            r"\bpay\b",
            r"\binstallment\b",
            r"\bschedule\b",
            r"\binvoice\b",
        ),
    ),
    (
        "demo",
        (
            r"\bdemo\b",
            r"\blog ?in\b",
            r"\bsign ?in\b",
            r"\bseed\b",
            r"\bhow (do|to) (i )?(use|start|explore)\b",
            r"\bnavigat",
            r"\bdashboard\b",
        ),
    ),
    (
        "policy",
        (
            r"\bpolic(y|ies)\b",
            r"\bendorsement\b",
            r"\bbind\b",
            r"\bcancel\b",
            r"\breinstate\b",
        ),
    ),
]


def chat_enabled() -> bool:
    return bool(settings.CHAT_WIDGET_ENABLED)


def ensure_chat_enabled() -> None:
    if not chat_enabled():
        raise ForbiddenError(
            "Live chat is disabled.",
            code="CHAT_DISABLED",
        )


def detect_escalation(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(p, lowered) for p in _ESCALATION_PATTERNS)


def detect_return_to_ai(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(p, lowered) for p in _RETURN_TO_AI_PATTERNS)


def match_intent(text: str) -> str:
    lowered = text.lower()
    for key, patterns in _INTENT_MAP:
        if any(re.search(p, lowered) for p in patterns):
            return key
    return "fallback"


def welcome_message(*, authenticated: bool, first_name: str | None = None) -> str:
    if authenticated and first_name:
        return (
            f"Hi {first_name} — I'm the InsureCo virtual assistant. I can help "
            "with your policies, claims, billing, or how to use the portal. "
            'Ask a question, or say "talk to a representative" for Member Services.'
        )
    return (
        "Hi — I'm the InsureCo virtual assistant. I can help with quotes, "
        "coverage, claims, billing, and using this demo. Ask a question, or "
        'say "talk to a representative" to reach a person.'
    )


def ai_reply(text: str, *, context: str | None, authenticated: bool) -> str:
    intent = match_intent(text)
    customer = authenticated or context == "customer_dashboard"

    if intent == "greeting":
        return (
            "Hello! Ask me about quotes, coverage types, filing a claim, "
            "billing, or how to explore this demo."
        )
    if intent == "quote":
        if customer:
            return (
                "To start a quote, open Quotes → New quote from your dashboard. "
                "You'll pick a line of business, answer rating questions, and "
                "see an itemized premium. I can't invent policy numbers or rates here."
            )
        return (
            "Register or use a demo customer login, then go to Quotes → New quote. "
            "The rating engine returns an explainable premium with itemized factors. "
            "I won't invent rates or policy numbers in chat."
        )
    if intent == "coverage":
        return (
            "InsureCo covers auto, home, and life. Each line has its own rating "
            "inputs, schedules, and claim types. Explore Quotes or Policies after "
            "signing in as a customer or agent."
        )
    if intent == "claim":
        if customer:
            return (
                "To file a claim, open Claims → File a claim and select the policy. "
                "You'll walk through loss details; adjusters then investigate, "
                "request info, approve, or reject. Status updates show on the claim timeline."
            )
        return (
            "Customers file claims from Claims → File a claim after signing in. "
            "Staff adjusters work the queue with fraud scoring, notes, and payouts. "
            "Try the demo Adjuster login to see adjudication."
        )
    if intent == "billing":
        if customer:
            return (
                "Open a policy to see the premium schedule and record a payment. "
                "Overdue installments are flagged by a scheduled job; policies can "
                "lapse after the configured grace period."
            )
        return (
            "Billing uses premium schedules and recorded payments. Sign in as a "
            "customer to view schedules, or as staff to record payments on a policy."
        )
    if intent == "policy":
        if customer:
            return (
                "Your Policies page lists coverage you hold. Agents can endorse, "
                "cancel, or reinstate; customers can review documents and billing. "
                "I can't look up a specific policy number in this chat."
            )
        return (
            "Policies move from quote → bind → active, with endorsements, cancel, "
            "and reinstate. Use a demo Agent or Customer login to walk the lifecycle."
        )
    if intent == "demo":
        return (
            "On the landing page, use one-click demo logins (Customer, Agent, "
            "Adjuster, Manager) when demo mode is on. API docs are at /api/docs; "
            "MailHog (:8025) and MinIO (:9001) are available locally."
        )
    return (
        "I'm not sure I follow. Try asking about quotes, coverage, claims, "
        "billing, or the demo. Or say \"talk to a representative\" for Member Services."
    )


def human_reply(text: str, *, authenticated: bool) -> str:
    intent = match_intent(text)
    if intent == "greeting":
        return (
            f"Hi, this is {HUMAN_AGENT_NAME} with {HUMAN_AGENT_TITLE}. "
            "How can I help you today?"
        )
    if intent == "claim":
        return (
            "I can walk you through filing or checking a claim in the portal. "
            "Open Claims from the sidebar after you sign in as a customer. "
            "If you need a status update, an adjuster will post notes on the claim."
        )
    if intent == "billing":
        return (
            "For billing questions, open your policy's premium schedule. "
            "You can record a payment there in this demo. Card charges are not "
            "processed — payments are recorded for workflow practice only."
        )
    if intent == "quote" or intent == "coverage":
        return (
            "Happy to help with coverage questions. Auto, home, and life are "
            "available; start a quote from the customer or agent dashboard for "
            "an actual rated premium."
        )
    if intent == "demo":
        return (
            "This chat is part of the InsureCo demo. Use the landing-page demo "
            "logins to switch roles. Say \"return to assistant\" anytime to go "
            "back to the virtual assistant."
        )
    if intent == "policy":
        return (
            "I can point you to Policies in the portal for documents and status. "
            "I won't invent policy numbers or personal details in this chat."
        )
    return (
        f"Thanks for reaching out — {HUMAN_AGENT_NAME} here. Could you share a "
        "bit more about what you need (quote, claim, billing, or navigation)? "
        'Say "return to assistant" to switch back to the virtual assistant.'
    )


def escalation_system_message() -> str:
    return f"Connecting you to a representative… Connected to {HUMAN_AGENT_DISPLAY}."


def return_to_ai_system_message() -> str:
    return "You've been returned to the InsureCo virtual assistant."


def _assert_visitor_or_customer(user: User | None) -> None:
    if user is None:
        return
    if user.role != UserRole.customer:
        raise ForbiddenError(
            "Live chat is available to visitors and customers only.",
            code="CHAT_ROLE_FORBIDDEN",
        )


async def _get_session(
    db: AsyncSession,
    session_id: uuid.UUID,
    actor: User | None,
) -> ChatSession:
    session = await db.scalar(
        select(ChatSession)
        .where(ChatSession.id == session_id)
        .options(selectinload(ChatSession.messages))
    )
    if session is None:
        raise NotFoundError("Chat session not found.", code="CHAT_SESSION_NOT_FOUND")

    if session.user_id is not None:
        if actor is None or actor.id != session.user_id:
            raise ForbiddenError(
                "You do not have access to this chat session.",
                code="CHAT_SESSION_FORBIDDEN",
            )
    return session


async def start_session(
    db: AsyncSession,
    *,
    context: Context,
    actor: User | None,
) -> ChatSession:
    ensure_chat_enabled()
    _assert_visitor_or_customer(actor)

    session = ChatSession(
        user_id=actor.id if actor else None,
        mode=ChatSessionMode.ai,
        agent_name=None,
        context=context,
    )
    db.add(session)
    await db.flush()

    welcome = welcome_message(
        authenticated=actor is not None,
        first_name=actor.first_name if actor else None,
    )
    db.add(
        ChatMessage(
            session_id=session.id,
            role=ChatMessageRole.assistant,
            body=welcome,
            sender_kind="ai",
        )
    )
    await db.commit()
    return await _get_session(db, session.id, actor)


async def get_session(
    db: AsyncSession,
    session_id: uuid.UUID,
    actor: User | None,
) -> ChatSession:
    ensure_chat_enabled()
    _assert_visitor_or_customer(actor)
    return await _get_session(db, session_id, actor)


async def escalate(
    db: AsyncSession,
    session_id: uuid.UUID,
    actor: User | None,
) -> ChatSession:
    ensure_chat_enabled()
    _assert_visitor_or_customer(actor)
    session = await _get_session(db, session_id, actor)

    if session.mode == ChatSessionMode.human:
        return session

    session.mode = ChatSessionMode.human
    session.agent_name = HUMAN_AGENT_DISPLAY
    db.add(
        ChatMessage(
            session_id=session.id,
            role=ChatMessageRole.system,
            body=escalation_system_message(),
            sender_kind=None,
        )
    )
    db.add(
        ChatMessage(
            session_id=session.id,
            role=ChatMessageRole.assistant,
            body=(
                f"Hi, this is {HUMAN_AGENT_NAME} with {HUMAN_AGENT_TITLE}. "
                "Thanks for waiting — how can I help?"
            ),
            sender_kind="human",
        )
    )
    await db.commit()
    return await _get_session(db, session.id, actor)


async def send_message(
    db: AsyncSession,
    session_id: uuid.UUID,
    body: str,
    actor: User | None,
) -> tuple[ChatSession, ChatMessage, ChatMessage]:
    ensure_chat_enabled()
    _assert_visitor_or_customer(actor)
    session = await _get_session(db, session_id, actor)

    text = body.strip()
    if not text:
        raise AppError("Message cannot be empty.", code="CHAT_EMPTY_MESSAGE")

    user_msg = ChatMessage(
        session_id=session.id,
        role=ChatMessageRole.user,
        body=text,
        sender_kind=None,
    )
    db.add(user_msg)
    await db.flush()

    authenticated = actor is not None

    # Mode transitions driven by intent.
    if session.mode == ChatSessionMode.ai and detect_escalation(text):
        session.mode = ChatSessionMode.human
        session.agent_name = HUMAN_AGENT_DISPLAY
        db.add(
            ChatMessage(
                session_id=session.id,
                role=ChatMessageRole.system,
                body=escalation_system_message(),
                sender_kind=None,
            )
        )
        reply_body = (
            f"Hi, this is {HUMAN_AGENT_NAME} with {HUMAN_AGENT_TITLE}. "
            "Thanks for waiting — how can I help?"
        )
        sender_kind = "human"
    elif session.mode == ChatSessionMode.human and detect_return_to_ai(text):
        session.mode = ChatSessionMode.ai
        session.agent_name = None
        db.add(
            ChatMessage(
                session_id=session.id,
                role=ChatMessageRole.system,
                body=return_to_ai_system_message(),
                sender_kind=None,
            )
        )
        reply_body = (
            "You're back with the virtual assistant. Ask about quotes, claims, "
            "billing, or the demo anytime."
        )
        sender_kind = "ai"
    elif session.mode == ChatSessionMode.human:
        reply_body = human_reply(text, authenticated=authenticated)
        sender_kind = "human"
    else:
        reply_body = ai_reply(
            text, context=session.context, authenticated=authenticated
        )
        sender_kind = "ai"

    reply = ChatMessage(
        session_id=session.id,
        role=ChatMessageRole.assistant,
        body=reply_body,
        sender_kind=sender_kind,
    )
    db.add(reply)
    await db.commit()

    refreshed = await _get_session(db, session.id, actor)
    # Re-fetch message rows after commit (ids + timestamps).
    user_fresh = next(m for m in refreshed.messages if m.id == user_msg.id)
    reply_fresh = next(m for m in refreshed.messages if m.id == reply.id)
    return refreshed, user_fresh, reply_fresh
