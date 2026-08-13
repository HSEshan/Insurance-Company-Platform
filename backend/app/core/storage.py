"""MinIO object storage: bucket bootstrap and presigned URL generation.

Files never pass through the API. The frontend asks for a presigned ``PUT``,
uploads straight to MinIO, then reports the metadata back to us. Downloads work
the same way in reverse with a short-lived presigned ``GET``.

The ``minio`` SDK is synchronous. Signing is a pure local computation (HMAC over
the request) once the region is pinned, so it is safe to call from async request
handlers. The calls that do hit the network — bucket creation, stat, and object
removal — are pushed onto a worker thread so they never block the event loop.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache

from anyio import to_thread
from minio import Minio
from minio.deleteobjects import DeleteObject

from app.core.config import settings


@dataclass(frozen=True)
class StoredObject:
    key: str
    last_modified: datetime | None
    size: int


class Bucket(enum.StrEnum):
    """Buckets from specs.md §6.6, each with its own retention policy."""

    policy_documents = "policy-documents"
    claim_documents = "claim-documents"
    customer_documents = "customer-documents"
    temp_uploads = "temp-uploads"


def _build_client(endpoint: str, *, secure: bool) -> Minio:
    # An explicit region matters: without one the SDK resolves it by calling
    # GET /<bucket>?location= before it can sign anything. The presign client
    # points at a browser-facing address the backend cannot reach, so that
    # lookup would fail and take every presign request down with it.
    return Minio(
        endpoint,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=secure,
        region=settings.MINIO_REGION,
    )


@lru_cache
def get_client() -> Minio:
    """Client for server-side operations, over the internal network.

    Always HTTP: inside Compose the backend talks to ``minio:9000`` on the
    Docker network. TLS for browsers terminates at host Nginx on the public
    ``files.*`` host — see ``get_presign_client``.
    """
    return _build_client(settings.MINIO_ENDPOINT, secure=False)


@lru_cache
def get_presign_client() -> Minio:
    """Client used only to sign URLs the browser will follow.

    A presigned URL's signature covers the host header, so it must be signed
    against the endpoint the browser will actually connect to. Inside Docker the
    backend reaches MinIO at ``minio:9000``, which does not resolve on the
    user's machine — signing with that host would produce URLs that always fail.

    ``MINIO_USE_SSL`` controls the scheme on those public URLs (``https://``
    behind Nginx TLS; ``http://`` for local MinIO on localhost:9000).
    """
    return _build_client(
        settings.MINIO_PUBLIC_ENDPOINT, secure=settings.MINIO_USE_SSL
    )


def _presign_expiry() -> timedelta:
    return timedelta(minutes=settings.PRESIGNED_URL_EXPIRY_MINUTES)


async def ensure_buckets() -> None:
    """Create any missing buckets. Safe to call on every startup."""

    def _ensure() -> None:
        client = get_client()
        for bucket in Bucket:
            if not client.bucket_exists(bucket.value):
                client.make_bucket(bucket.value)

    await to_thread.run_sync(_ensure)


def presigned_put_url(bucket: str, key: str) -> str:
    return get_presign_client().presigned_put_object(
        bucket, key, expires=_presign_expiry()
    )


def presigned_get_url(bucket: str, key: str, *, file_name: str | None = None) -> str:
    # Force a download with the original filename rather than the opaque
    # storage key, which is a UUID path.
    response_headers = (
        {"response-content-disposition": f'attachment; filename="{file_name}"'}
        if file_name
        else None
    )
    return get_presign_client().presigned_get_object(
        bucket,
        key,
        expires=_presign_expiry(),
        response_headers=response_headers,
    )


async def put_object(bucket: str, key: str, data: bytes, content_type: str) -> None:
    """Upload bytes the server itself produced, e.g. a generated PDF."""

    def _put() -> None:
        from io import BytesIO

        get_client().put_object(
            bucket, key, BytesIO(data), length=len(data), content_type=content_type
        )

    await to_thread.run_sync(_put)


async def list_objects(bucket: str, *, prefix: str = "") -> list[StoredObject]:
    """List objects in a bucket (non-recursive prefixes included)."""

    def _list() -> list[StoredObject]:
        return [
            StoredObject(
                key=obj.object_name,
                last_modified=obj.last_modified,
                size=obj.size or 0,
            )
            for obj in get_client().list_objects(bucket, prefix=prefix, recursive=True)
            if obj.object_name
        ]

    return await to_thread.run_sync(_list)


async def remove_object(bucket: str, key: str) -> None:
    await to_thread.run_sync(get_client().remove_object, bucket, key)


async def remove_objects(bucket: str, keys: list[str]) -> None:
    def _remove() -> None:
        errors = get_client().remove_objects(
            bucket, [DeleteObject(k) for k in keys]
        )
        # remove_objects returns a lazy generator; consume it so deletes happen.
        for _ in errors:
            pass

    await to_thread.run_sync(_remove)


async def object_exists(bucket: str, key: str) -> bool:
    """Confirm an upload actually landed before recording its metadata."""

    def _stat() -> bool:
        from minio.error import S3Error

        try:
            get_client().stat_object(bucket, key)
        except S3Error:
            return False
        return True

    return await to_thread.run_sync(_stat)


async def object_size(bucket: str, key: str) -> int | None:
    """Server-side size of an uploaded object, or ``None`` if it is missing."""

    def _stat() -> int | None:
        from minio.error import S3Error

        try:
            return get_client().stat_object(bucket, key).size
        except S3Error:
            return None

    return await to_thread.run_sync(_stat)


async def check_connection() -> bool:
    """Readiness probe helper."""

    def _check() -> bool:
        try:
            get_client().bucket_exists(Bucket.temp_uploads.value)
        except Exception:
            return False
        return True

    return await to_thread.run_sync(_check)
