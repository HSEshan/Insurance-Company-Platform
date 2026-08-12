"""Unit tests for document storage keys, bucket routing, and upload validation."""

from __future__ import annotations

import uuid

import pytest

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.storage import Bucket
from app.models.enums import DocumentOwnerType
from app.services.document_service import (
    bucket_for,
    build_storage_key,
    validate_upload,
)


def test_each_owner_type_routes_to_a_bucket() -> None:
    for owner_type in DocumentOwnerType:
        assert bucket_for(owner_type) in {b.value for b in Bucket}


def test_claims_and_policies_use_separate_buckets() -> None:
    assert bucket_for(DocumentOwnerType.claim) == Bucket.claim_documents.value
    assert bucket_for(DocumentOwnerType.policy) == Bucket.policy_documents.value


def test_storage_key_is_owner_scoped_and_keeps_the_extension() -> None:
    owner_id = uuid.uuid4()
    key = build_storage_key(DocumentOwnerType.claim, owner_id, "damage photo.JPG")

    assert key.startswith(f"claim/{owner_id}/")
    assert key.endswith(".jpg")


def test_storage_key_is_unique_per_call() -> None:
    owner_id = uuid.uuid4()
    keys = {
        build_storage_key(DocumentOwnerType.claim, owner_id, "estimate.pdf")
        for _ in range(50)
    }
    assert len(keys) == 50


def test_storage_key_discards_client_supplied_path() -> None:
    owner_id = uuid.uuid4()
    key = build_storage_key(DocumentOwnerType.claim, owner_id, "../../etc/passwd")

    assert key.startswith(f"claim/{owner_id}/")
    assert ".." not in key


def test_validate_upload_accepts_a_normal_photo() -> None:
    validate_upload("image/jpeg", 2 * 1024 * 1024)


def test_validate_upload_rejects_executable_mime_type() -> None:
    with pytest.raises(AppError) as exc:
        validate_upload("application/x-msdownload", 1024)
    assert exc.value.code == "UNSUPPORTED_MEDIA_TYPE"
    assert exc.value.status_code == 415


def test_validate_upload_rejects_oversized_file() -> None:
    with pytest.raises(AppError) as exc:
        validate_upload("application/pdf", settings.max_upload_size_bytes + 1)
    assert exc.value.code == "FILE_TOO_LARGE"
    assert exc.value.status_code == 413


def test_upload_limit_matches_configured_megabytes() -> None:
    assert settings.max_upload_size_bytes == settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
