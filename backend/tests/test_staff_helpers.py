"""Unit tests for staff admin helpers (no database required)."""

from __future__ import annotations

from app.services.staff_service import generate_temp_password


def test_generate_temp_password_length_and_charset() -> None:
    pwd = generate_temp_password(16)
    assert len(pwd) == 16
    assert pwd.isalnum()
    # Ambiguous characters are excluded for supportability.
    assert "O" not in pwd
    assert "0" not in pwd
    assert "l" not in pwd
    assert "I" not in pwd


def test_generate_temp_password_unique() -> None:
    samples = {generate_temp_password() for _ in range(20)}
    assert len(samples) == 20
