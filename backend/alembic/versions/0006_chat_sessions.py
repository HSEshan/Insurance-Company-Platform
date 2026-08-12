"""Add chat_sessions / chat_messages for the demo live-chat widget.

Revision ID: 0006_chat
Revises: 0005_must_reset
Create Date: 2026-08-10

Idempotent: fresh DBs already get these tables from ``metadata.create_all``
in ``0001_initial`` once the models are registered.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_chat"
down_revision: str | None = "0005_must_reset"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

chat_session_mode = postgresql.ENUM(
    "ai", "human", name="chat_session_mode", create_type=False
)
chat_message_role = postgresql.ENUM(
    "user", "assistant", "system", name="chat_message_role", create_type=False
)


def _table_names() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return set(inspector.get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    tables = _table_names()

    # Create enum types if missing (idempotent).
    for type_name, values in (
        ("chat_session_mode", ("ai", "human")),
        ("chat_message_role", ("user", "assistant", "system")),
    ):
        exists = bind.execute(
            sa.text("SELECT 1 FROM pg_type WHERE typname = :n"),
            {"n": type_name},
        ).scalar()
        if not exists:
            sa.Enum(*values, name=type_name).create(bind, checkfirst=True)

    if "chat_sessions" not in tables:
        op.create_table(
            "chat_sessions",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("user_id", sa.UUID(), nullable=True),
            sa.Column("mode", chat_session_mode, nullable=False),
            sa.Column("agent_name", sa.String(length=120), nullable=True),
            sa.Column("context", sa.String(length=40), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )

    if "chat_messages" not in tables:
        op.create_table(
            "chat_messages",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("session_id", sa.UUID(), nullable=False),
            sa.Column("role", chat_message_role, nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("sender_kind", sa.String(length=20), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["session_id"], ["chat_sessions.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_chat_messages_session_id", "chat_messages", ["session_id"]
        )


def downgrade() -> None:
    tables = _table_names()
    if "chat_messages" in tables:
        op.drop_index("ix_chat_messages_session_id", table_name="chat_messages")
        op.drop_table("chat_messages")
    if "chat_sessions" in tables:
        op.drop_table("chat_sessions")

    bind = op.get_bind()
    for type_name in ("chat_message_role", "chat_session_mode"):
        exists = bind.execute(
            sa.text("SELECT 1 FROM pg_type WHERE typname = :n"),
            {"n": type_name},
        ).scalar()
        if exists:
            sa.Enum(name=type_name).drop(bind, checkfirst=True)
