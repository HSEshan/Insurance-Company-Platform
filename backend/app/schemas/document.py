"""Document request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DocumentOwnerType, DocumentType


class DocumentPresignRequest(BaseModel):
    owner_type: DocumentOwnerType
    owner_id: uuid.UUID
    document_type: DocumentType
    file_name: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=100)
    file_size_bytes: int = Field(gt=0)


class DocumentPresignResponse(BaseModel):
    upload_url: str
    storage_bucket: str
    storage_key: str
    expires_in_seconds: int


class DocumentCreate(BaseModel):
    """Recorded after the browser has uploaded to the presigned URL."""

    owner_type: DocumentOwnerType
    owner_id: uuid.UUID
    document_type: DocumentType
    file_name: str = Field(min_length=1, max_length=255)
    mime_type: str | None = Field(default=None, max_length=100)
    storage_bucket: str = Field(min_length=1, max_length=100)
    storage_key: str = Field(min_length=1)
    file_size_bytes: int | None = Field(default=None, ge=0)
    checksum_sha256: str | None = Field(default=None, max_length=64)


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_type: DocumentOwnerType
    owner_id: uuid.UUID
    document_type: DocumentType
    file_name: str
    mime_type: str | None = None
    storage_bucket: str
    file_size_bytes: int | None = None
    checksum_sha256: str | None = None
    uploaded_by: uuid.UUID | None = None
    is_verified: bool
    verified_by: uuid.UUID | None = None
    created_at: datetime


class DocumentDownload(BaseModel):
    download_url: str
    file_name: str
    expires_in_seconds: int
