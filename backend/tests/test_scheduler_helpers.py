"""Unit tests for scheduler helper rules (no database required)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.services.scheduler_service import _is_older_than


def test_naive_timestamps_are_treated_as_utc() -> None:
    cutoff = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    naive = datetime(2026, 8, 1, 11, 0)
    assert _is_older_than(naive, cutoff) is True


def test_aware_timestamps_compare_correctly() -> None:
    cutoff = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    newer = datetime(2026, 8, 1, 13, 0, tzinfo=UTC)
    older = datetime(2026, 8, 1, 11, 0, tzinfo=UTC)
    assert _is_older_than(newer, cutoff) is False
    assert _is_older_than(older, cutoff) is True


def test_missing_timestamp_is_not_treated_as_stale() -> None:
    cutoff = datetime.now(UTC)
    assert _is_older_than(None, cutoff) is False


def test_orphan_grace_is_shorter_than_a_day() -> None:
    # The grace window must be short enough that abandoned uploads don't pile
    # up, but long enough that an in-flight metadata POST is never raced.
    assert timedelta(minutes=settings.ORPHAN_OBJECT_GRACE_MINUTES) < timedelta(hours=24)
    assert settings.ORPHAN_OBJECT_GRACE_MINUTES >= 15


def test_lapse_window_matches_spec_default() -> None:
    assert settings.PREMIUM_LAPSE_DAYS == 30


def test_celery_urls_use_separate_redis_databases() -> None:
    # Lockout counters live on db 0; broker/results must not share that space.
    assert settings.celery_broker_url.endswith("/1")
    assert settings.celery_result_backend.endswith("/2")
    assert settings.celery_broker_url != str(settings.REDIS_URL)
