"""Unit tests for the security primitives (no database required)."""

from __future__ import annotations

import time

import jwt
import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    decrypt_pii,
    encrypt_pii,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("Sup3rSecret!")
    assert hashed != "Sup3rSecret!"
    assert verify_password("Sup3rSecret!", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_password_verify_handles_invalid_hash() -> None:
    assert verify_password("anything", "not-a-real-hash") is False


def test_access_token_contains_expected_claims() -> None:
    token = create_access_token("user-123", extra_claims={"role": "agent"})
    payload = decode_token(token)
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"
    assert payload["role"] == "agent"
    assert "jti" in payload


def test_refresh_token_type() -> None:
    payload = decode_token(create_refresh_token("user-123"))
    assert payload["type"] == "refresh"


def test_decode_rejects_tampered_token() -> None:
    token = create_access_token("user-123")
    with pytest.raises(jwt.PyJWTError):
        decode_token(token + "tampered")


def test_pii_encryption_roundtrip() -> None:
    ciphertext = encrypt_pii("123456789")
    assert ciphertext is not None
    assert ciphertext != "123456789"
    assert decrypt_pii(ciphertext) == "123456789"


def test_pii_encryption_handles_none_and_empty() -> None:
    assert encrypt_pii(None) is None
    assert encrypt_pii("") is None
    assert decrypt_pii(None) is None


def test_decrypt_invalid_token_returns_none() -> None:
    assert decrypt_pii("garbage-not-fernet") is None


def test_tokens_have_distinct_jti() -> None:
    t1 = decode_token(create_access_token("u"))
    time.sleep(0.01)
    t2 = decode_token(create_access_token("u"))
    assert t1["jti"] != t2["jti"]
