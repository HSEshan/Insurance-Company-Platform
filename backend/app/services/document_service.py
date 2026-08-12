"""Document metadata lifecycle on top of MinIO object storage.

Bytes never touch the API. This service authorizes the request, hands out a
short-lived presigned URL, and records the metadata once the browser confirms
the upload landed.
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import PurePosixPath

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.config import settings
from app.core.exceptions import AppError, ForbiddenError, NotFoundError
from app.core.storage import Bucket
from app.models.customer import Customer
from app.models.document import Document
from app.models.enums import DocumentOwnerType, DocumentType, UserRole
from app.models.user import User
from app.schemas.document import (
    DocumentCreate,
    DocumentDownload,
    DocumentPresignRequest,
    DocumentPresignResponse,
)
from app.services import audit_service, claim_service, policy_service, quote_service

# Quote-stage attachments are underwriting evidence about the applicant, so they
# live with the customer's documents rather than in the bound-policy bucket.
_BUCKET_BY_OWNER: dict[DocumentOwnerType, Bucket] = {
    DocumentOwnerType.policy: Bucket.policy_documents,
    DocumentOwnerType.claim: Bucket.claim_documents,
    DocumentOwnerType.customer: Bucket.customer_documents,
    DocumentOwnerType.quote: Bucket.customer_documents,
}

# Whitelist per specs.md §10 "Input Validation". Everything a claimant or
# underwriter realistically attaches: photos, scans, and reports.
_ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/heic",
        "image/tiff",
        "application/pdf",
        "text/plain",
    }
)

_VERIFIERS: frozenset[UserRole] = frozenset(
    {UserRole.agent, UserRole.adjuster, UserRole.manager, UserRole.super_admin}
)

_MANAGERS: frozenset[UserRole] = frozenset({UserRole.manager, UserRole.super_admin})

_DELETERS: frozenset[UserRole] = frozenset(
    {UserRole.agent, UserRole.manager, UserRole.super_admin}
)


def bucket_for(owner_type: DocumentOwnerType) -> str:
    return _BUCKET_BY_OWNER[owner_type].value


def build_storage_key(
    owner_type: DocumentOwnerType, owner_id: uuid.UUID, file_name: str
) -> str:
    """Namespace objects by owner and give each a unique, unguessable name.

    The original filename is never used as the key: it may contain path
    separators or duplicate an existing object. It is preserved as metadata and
    reattached via content-disposition on download.
    """
    suffix = PurePosixPath(file_name).suffix.lower()[:16]
    return f"{owner_type.value}/{owner_id}/{uuid.uuid4().hex}{suffix}"


def validate_upload(mime_type: str, file_size_bytes: int) -> None:
    if mime_type not in _ALLOWED_MIME_TYPES:
        raise AppError(
            f"File type '{mime_type}' is not accepted. Allowed types: "
            f"{', '.join(sorted(_ALLOWED_MIME_TYPES))}.",
            code="UNSUPPORTED_MEDIA_TYPE",
            status_code=415,
        )
    if file_size_bytes > settings.max_upload_size_bytes:
        raise AppError(
            f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB upload limit.",
            code="FILE_TOO_LARGE",
            status_code=413,
        )


async def assert_owner_access(
    db: AsyncSession,
    owner_type: DocumentOwnerType,
    owner_id: uuid.UUID,
    actor: User,
) -> None:
    """Authorize against the owning entity, reusing each module's own rules.

    Documents inherit the visibility of whatever they are attached to, so a
    customer who cannot see a claim cannot see or add its documents either.
    """
    if owner_type == DocumentOwnerType.claim:
        claim = await claim_service.get_claim(db, owner_id)
        await claim_service.assert_claim_access(db, claim, actor)
    elif owner_type == DocumentOwnerType.policy:
        policy = await policy_service.get_policy(db, owner_id)
        await policy_service.assert_policy_access(db, policy, actor)
    elif owner_type == DocumentOwnerType.quote:
        quote = await quote_service.get_quote(db, owner_id)
        await quote_service.assert_quote_access(db, quote, actor)
    elif owner_type == DocumentOwnerType.customer:
        await _assert_customer_access(db, owner_id, actor)


async def _assert_customer_access(
    db: AsyncSession, customer_id: uuid.UUID, actor: User
) -> None:
    customer = await db.scalar(select(Customer).where(Customer.id == customer_id))
    if customer is None:
        raise NotFoundError("Customer not found.", code="CUSTOMER_NOT_FOUND")
    if actor.role in {
        UserRole.agent,
        UserRole.adjuster,
        UserRole.manager,
        UserRole.super_admin,
    }:
        return
    if actor.role == UserRole.customer and customer.user_id == actor.id:
        return
    raise ForbiddenError("You do not have access to this customer's documents.")


async def presign_upload(
    db: AsyncSession, actor: User, payload: DocumentPresignRequest
) -> DocumentPresignResponse:
    await assert_owner_access(db, payload.owner_type, payload.owner_id, actor)
    validate_upload(payload.mime_type, payload.file_size_bytes)

    bucket = bucket_for(payload.owner_type)
    key = build_storage_key(payload.owner_type, payload.owner_id, payload.file_name)
    return DocumentPresignResponse(
        upload_url=storage.presigned_put_url(bucket, key),
        storage_bucket=bucket,
        storage_key=key,
        expires_in_seconds=settings.PRESIGNED_URL_EXPIRY_MINUTES * 60,
    )


async def record_document(
    db: AsyncSession, actor: User, payload: DocumentCreate
) -> Document:
    """Persist metadata for an object the client has already uploaded."""
    await assert_owner_access(db, payload.owner_type, payload.owner_id, actor)

    expected_bucket = bucket_for(payload.owner_type)
    if payload.storage_bucket != expected_bucket:
        raise AppError(
            "storage_bucket does not match the owner type.",
            code="INVALID_STORAGE_BUCKET",
            status_code=422,
        )
    # The key is issued by presign_upload and is owner-scoped. Re-checking the
    # prefix stops a caller from attaching someone else's object to their own
    # record by passing an arbitrary key.
    if not payload.storage_key.startswith(
        f"{payload.owner_type.value}/{payload.owner_id}/"
    ):
        raise AppError(
            "storage_key does not belong to this owner.",
            code="INVALID_STORAGE_KEY",
            status_code=422,
        )

    # Trust the object store over the client for existence and size.
    size = await storage.object_size(expected_bucket, payload.storage_key)
    if size is None:
        raise AppError(
            "No uploaded file was found for that storage key.",
            code="UPLOAD_NOT_FOUND",
            status_code=409,
        )
    if size > settings.max_upload_size_bytes:
        await storage.remove_object(expected_bucket, payload.storage_key)
        raise AppError(
            f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB upload limit.",
            code="FILE_TOO_LARGE",
            status_code=413,
        )

    document = Document(
        owner_type=payload.owner_type,
        owner_id=payload.owner_id,
        document_type=payload.document_type,
        file_name=payload.file_name,
        mime_type=payload.mime_type,
        storage_bucket=expected_bucket,
        storage_key=payload.storage_key,
        file_size_bytes=size,
        checksum_sha256=payload.checksum_sha256,
        uploaded_by=actor.id,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)
    return document


async def store_generated_document(
    db: AsyncSession,
    *,
    owner_type: DocumentOwnerType,
    owner_id: uuid.UUID,
    document_type: DocumentType,
    file_name: str,
    content: bytes,
    mime_type: str = "application/pdf",
    actor_id: uuid.UUID | None = None,
    replace_existing: bool = False,
) -> Document:
    """Store bytes the system generated itself, bypassing the presign flow.

    Unlike an uploaded file this content is trusted, so there is no owner
    authorization check here — callers are lifecycle events that have already
    been authorized. Generated documents are marked verified because the system
    is their author.
    """
    bucket = bucket_for(owner_type)
    key = build_storage_key(owner_type, owner_id, file_name)
    await storage.put_object(bucket, key, content, mime_type)

    if replace_existing:
        # A declaration page supersedes any earlier one, so drop the old rows
        # (and their objects) rather than accumulating near-duplicates.
        superseded = list(
            (
                await db.scalars(
                    select(Document).where(
                        Document.owner_type == owner_type,
                        Document.owner_id == owner_id,
                        Document.document_type == document_type,
                    )
                )
            ).all()
        )
        stale = [(d.storage_bucket, d.storage_key) for d in superseded]
        for old in superseded:
            await db.delete(old)
    else:
        stale = []

    document = Document(
        owner_type=owner_type,
        owner_id=owner_id,
        document_type=document_type,
        file_name=file_name,
        mime_type=mime_type,
        storage_bucket=bucket,
        storage_key=key,
        file_size_bytes=len(content),
        checksum_sha256=hashlib.sha256(content).hexdigest(),
        uploaded_by=actor_id,
        is_verified=True,
        verified_by=actor_id,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    for old_bucket, old_key in stale:
        await storage.remove_object(old_bucket, old_key)
    return document


async def get_document(db: AsyncSession, document_id: uuid.UUID) -> Document:
    document = await db.scalar(select(Document).where(Document.id == document_id))
    if document is None:
        raise NotFoundError("Document not found.", code="DOCUMENT_NOT_FOUND")
    return document


async def list_documents(
    db: AsyncSession,
    actor: User,
    *,
    owner_type: DocumentOwnerType,
    owner_id: uuid.UUID,
    document_type: DocumentType | None = None,
) -> list[Document]:
    await assert_owner_access(db, owner_type, owner_id, actor)

    stmt = select(Document).where(
        Document.owner_type == owner_type, Document.owner_id == owner_id
    )
    if document_type is not None:
        stmt = stmt.where(Document.document_type == document_type)
    stmt = stmt.order_by(Document.created_at.desc())
    return list((await db.scalars(stmt)).all())


async def count_documents(
    db: AsyncSession, owner_type: DocumentOwnerType, owner_id: uuid.UUID
) -> int:
    count = await db.scalar(
        select(func.count(Document.id)).where(
            Document.owner_type == owner_type, Document.owner_id == owner_id
        )
    )
    return int(count or 0)


async def build_download(
    db: AsyncSession, document_id: uuid.UUID, actor: User
) -> DocumentDownload:
    document = await get_document(db, document_id)
    await assert_owner_access(db, document.owner_type, document.owner_id, actor)
    return DocumentDownload(
        download_url=storage.presigned_get_url(
            document.storage_bucket,
            document.storage_key,
            file_name=document.file_name,
        ),
        file_name=document.file_name,
        expires_in_seconds=settings.PRESIGNED_URL_EXPIRY_MINUTES * 60,
    )


async def verify_document(
    db: AsyncSession, document_id: uuid.UUID, actor: User
) -> Document:
    document = await get_document(db, document_id)
    if actor.role not in _VERIFIERS:
        raise ForbiddenError("Only an agent, adjuster, or manager can verify documents.")
    await assert_owner_access(db, document.owner_type, document.owner_id, actor)

    document.is_verified = True
    document.verified_by = actor.id
    await audit_service.record(
        db,
        action="document.verified",
        entity_type="document",
        entity_id=document.id,
        actor=actor,
        new_value={
            "file_name": document.file_name,
            "owner_type": document.owner_type.value,
            "owner_id": str(document.owner_id),
        },
    )
    await db.commit()
    await db.refresh(document)
    return document


async def delete_document(
    db: AsyncSession, document_id: uuid.UUID, actor: User
) -> None:
    document = await get_document(db, document_id)
    if actor.role not in _DELETERS:
        raise ForbiddenError("Only an agent or manager can delete documents.")
    # A verified document is evidence someone has already signed off on; per
    # specs.md §6.6 removing it needs manager approval.
    if document.is_verified and actor.role not in _MANAGERS:
        raise ForbiddenError(
            "This document has been verified; only a manager can delete it."
        )
    await assert_owner_access(db, document.owner_type, document.owner_id, actor)

    bucket, key = document.storage_bucket, document.storage_key
    await audit_service.record(
        db,
        action="document.deleted",
        entity_type="document",
        entity_id=document.id,
        actor=actor,
        old_value={
            "file_name": document.file_name,
            "is_verified": document.is_verified,
            "owner_type": document.owner_type.value,
            "owner_id": str(document.owner_id),
        },
    )
    await db.delete(document)
    await db.commit()
    # Drop the object last: a stale object is recoverable, a metadata row
    # pointing at a deleted object is a broken download for the user.
    await storage.remove_object(bucket, key)
