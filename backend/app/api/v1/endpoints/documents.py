"""Document upload, download, verification, and deletion endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.enums import DocumentOwnerType, DocumentType
from app.models.user import User
from app.schemas.common import Envelope, ok
from app.schemas.document import (
    DocumentCreate,
    DocumentDownload,
    DocumentPresignRequest,
    DocumentPresignResponse,
    DocumentRead,
)
from app.services import document_service

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/presign-upload", response_model=Envelope[DocumentPresignResponse])
async def presign_upload(
    payload: DocumentPresignRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Issue a short-lived URL the browser uploads to directly."""
    result = await document_service.presign_upload(db, current_user, payload)
    return ok(result)


@router.post(
    "",
    response_model=Envelope[DocumentRead],
    status_code=status.HTTP_201_CREATED,
)
async def create_document(
    payload: DocumentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Record metadata for a file that has finished uploading."""
    document = await document_service.record_document(db, current_user, payload)
    return ok(DocumentRead.model_validate(document))


@router.get("", response_model=Envelope[list[DocumentRead]])
async def list_documents(
    owner_type: DocumentOwnerType = Query(...),
    owner_id: uuid.UUID = Query(...),
    document_type: DocumentType | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    documents = await document_service.list_documents(
        db,
        current_user,
        owner_type=owner_type,
        owner_id=owner_id,
        document_type=document_type,
    )
    return ok([DocumentRead.model_validate(d) for d in documents])


@router.get("/{document_id}/download", response_model=Envelope[DocumentDownload])
async def download_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return ok(await document_service.build_download(db, document_id, current_user))


@router.post("/{document_id}/verify", response_model=Envelope[DocumentRead])
async def verify_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    document = await document_service.verify_document(db, document_id, current_user)
    return ok(DocumentRead.model_validate(document))


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await document_service.delete_document(db, document_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
