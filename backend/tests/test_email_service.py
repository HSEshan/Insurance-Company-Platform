"""Unit tests for email dispatch gating."""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.services import email_service


@pytest.mark.asyncio
async def test_send_email_respects_feature_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "EMAIL_NOTIFICATIONS_ENABLED", False)
    called = {"n": 0}

    async def _boom(*_args, **_kwargs):
        called["n"] += 1
        raise AssertionError("SMTP should not be contacted when disabled")

    monkeypatch.setattr(email_service.aiosmtplib, "send", _boom)
    assert await email_service.send_email(to="a@b.com", subject="x", body="y") is False
    assert called["n"] == 0
