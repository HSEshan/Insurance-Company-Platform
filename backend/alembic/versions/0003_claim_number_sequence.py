"""Claim number sequence for Phase 3.

Revision ID: 0003_claim_seq
Revises: 0002_quote_policy
Create Date: 2026-08-06
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_claim_seq"
down_revision: str | None = "0002_quote_policy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS claim_number_seq START 1")


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS claim_number_seq")
