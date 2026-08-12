"""Unit tests for audit scrubbing and CSV shaping (no database required)."""

from __future__ import annotations

import uuid

from app.services.audit_service import ANONYMOUS_ENTITY_ID, scrub_value


def test_scrub_value_redacts_sensitive_keys() -> None:
    cleaned = scrub_value(
        {
            "status": "active",
            "ssn_last4": "6789",
            "ssn_encrypted": "cipher",
            "nested": {"password_hash": "x", "ok": 1},
            "tokens": [{"access_token": "abc", "role": "agent"}],
        }
    )
    assert cleaned["status"] == "active"
    assert cleaned["ssn_last4"] == "[REDACTED]"
    assert cleaned["ssn_encrypted"] == "[REDACTED]"
    assert cleaned["nested"]["password_hash"] == "[REDACTED]"
    assert cleaned["nested"]["ok"] == 1
    assert cleaned["tokens"][0]["access_token"] == "[REDACTED]"
    assert cleaned["tokens"][0]["role"] == "agent"


def test_scrub_value_stringifies_uuids() -> None:
    uid = uuid.uuid4()
    assert scrub_value({"id": uid}) == {"id": str(uid)}


def test_anonymous_entity_id_is_stable_nil() -> None:
    assert ANONYMOUS_ENTITY_ID == uuid.UUID(int=0)
