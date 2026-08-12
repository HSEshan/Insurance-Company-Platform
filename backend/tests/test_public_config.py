"""Public landing-page config helpers (no database required)."""

from __future__ import annotations

from app.api.v1.endpoints.public import _DEMO_PERSONAS
from app.models.enums import UserRole


def test_demo_personas_cover_reviewer_roles() -> None:
    roles = {p.role for p in _DEMO_PERSONAS}
    assert roles == {
        UserRole.customer,
        UserRole.agent,
        UserRole.adjuster,
        UserRole.manager,
    }
    assert all(p.password for p in _DEMO_PERSONAS)
    assert all("@insureco.com" in p.email for p in _DEMO_PERSONAS)


def test_public_config_schema_includes_chat_flag() -> None:
    from app.schemas.public import PublicConfig

    fields = PublicConfig.model_fields
    assert "chat_widget_enabled" in fields
    assert "demo_mode_enabled" in fields
