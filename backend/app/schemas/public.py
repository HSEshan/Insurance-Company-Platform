"""Public (unauthenticated) configuration schemas for the landing page."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr

from app.models.enums import UserRole


class DemoPersona(BaseModel):
    role: UserRole
    label: str
    email: EmailStr
    password: str
    description: str


class PublicConfig(BaseModel):
    app_name: str
    demo_mode_enabled: bool
    chat_widget_enabled: bool
    github_repo_url: str | None = None
    api_docs_path: str = "/api/docs"
    personas: list[DemoPersona] = []
