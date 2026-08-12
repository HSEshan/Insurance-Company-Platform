"""Unauthenticated endpoints for the portfolio landing page."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings
from app.models.enums import UserRole
from app.schemas.common import Envelope, ok
from app.schemas.public import DemoPersona, PublicConfig

router = APIRouter(prefix="/public", tags=["public"])

# Must stay in sync with ``scripts.seed`` demo accounts. Only returned when
# DEMO_MODE_ENABLED is on — never expose these in a real deployment.
_DEMO_PERSONAS: list[DemoPersona] = [
    DemoPersona(
        role=UserRole.customer,
        label="Demo Customer",
        email="customer@insureco.com",
        password="Customer123!",
        description="Policies, claims, billing, and notifications",
    ),
    DemoPersona(
        role=UserRole.agent,
        label="Demo Agent",
        email="agent@insureco.com",
        password="Agent123!",
        description="Quotes, binding, customers, and endorsements",
    ),
    DemoPersona(
        role=UserRole.adjuster,
        label="Demo Adjuster",
        email="adjuster@insureco.com",
        password="Adjuster123!",
        description="Claims queue and adjudication",
    ),
    DemoPersona(
        role=UserRole.manager,
        label="Demo Manager",
        email="manager@insureco.com",
        password="Manager123!",
        description="Approvals, reports, and audit log",
    ),
]


@router.get("/config", response_model=Envelope[PublicConfig])
async def public_config() -> dict:
    github = settings.GITHUB_REPO_URL.strip() or None
    return ok(
        PublicConfig(
            app_name=settings.APP_NAME,
            demo_mode_enabled=settings.DEMO_MODE_ENABLED,
            chat_widget_enabled=settings.CHAT_WIDGET_ENABLED,
            github_repo_url=github,
            api_docs_path="/api/docs",
            personas=_DEMO_PERSONAS if settings.DEMO_MODE_ENABLED else [],
        )
    )
