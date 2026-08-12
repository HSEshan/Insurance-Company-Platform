"""Document metadata model (files themselves live in MinIO)."""

from __future__ import annotations

import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import DocumentOwnerType, DocumentType


class Document(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "documents"

    owner_type: Mapped[DocumentOwnerType] = mapped_column(
        SQLEnum(DocumentOwnerType, name="document_owner_type"), nullable=False
    )
    # Polymorphic owner reference; integrity enforced at the service layer.
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    document_type: Mapped[DocumentType] = mapped_column(
        SQLEnum(DocumentType, name="document_type"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(100))
    storage_bucket: Mapped[str] = mapped_column(String(100), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    checksum_sha256: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
