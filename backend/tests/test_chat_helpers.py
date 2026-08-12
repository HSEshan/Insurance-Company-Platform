"""Pure helpers for the demo live-chat FAQ / escalation engine."""

from __future__ import annotations

from app.services.chat_service import (
    HUMAN_AGENT_DISPLAY,
    ai_reply,
    detect_escalation,
    detect_return_to_ai,
    escalation_system_message,
    human_reply,
    match_intent,
    welcome_message,
)


def test_escalation_keywords() -> None:
    assert detect_escalation("I want to talk to a representative")
    assert detect_escalation("Can I speak with a real person?")
    assert detect_escalation("Please connect me to an agent")
    assert not detect_escalation("How do I file a claim?")


def test_return_to_ai_keywords() -> None:
    assert detect_return_to_ai("return to the assistant")
    assert detect_return_to_ai("talk to the AI please")
    assert not detect_return_to_ai("I need help with billing")


def test_intent_map() -> None:
    assert match_intent("I'd like a quote for my car") == "quote"
    assert match_intent("How do I file a claim?") == "claim"
    assert match_intent("What about my payment schedule?") == "billing"
    assert match_intent("hello there") == "greeting"
    assert match_intent("asdf qwerty") == "fallback"


def test_ai_reply_does_not_invent_policy_numbers() -> None:
    reply = ai_reply("quote please", context="landing", authenticated=False)
    assert "AUTO-" not in reply
    assert "policy number" in reply.lower() or "rates" in reply.lower()


def test_ai_reply_customer_context() -> None:
    reply = ai_reply("file a claim", context="customer_dashboard", authenticated=True)
    assert "Claims" in reply
    assert "File a claim" in reply or "file" in reply.lower()


def test_welcome_authenticated() -> None:
    msg = welcome_message(authenticated=True, first_name="Jordan")
    assert "Jordan" in msg
    assert "representative" in msg


def test_human_persona_in_escalation_banner() -> None:
    assert HUMAN_AGENT_DISPLAY in escalation_system_message()
    assert "Alex" in human_reply("hello", authenticated=False)
