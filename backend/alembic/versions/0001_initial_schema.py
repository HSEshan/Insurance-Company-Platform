"""Initial baseline schema (all Phase 1+ tables).

This baseline migration materialises the full SQLAlchemy metadata so the
database matches the models in a single, deterministic step. Subsequent
schema changes should be produced with ``alembic revision --autogenerate``.

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-12

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from app.models import Base

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
