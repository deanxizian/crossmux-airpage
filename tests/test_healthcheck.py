from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.healthcheck import assess_health


@pytest.mark.parametrize("age,healthy", [(0, True), (60, True), (3600, False)])
def test_heartbeat_freshness_replaces_image_existence(settings, age, healthy) -> None:
    now = datetime(2026, 9, 5, tzinfo=UTC)
    then = (now - timedelta(seconds=age)).isoformat()
    (settings.output_dir / "airpage.bmp").write_bytes(b"old image")
    status = {
        "version": 1,
        "last_started_at": then,
        "last_completed_at": then,
        "last_rendered_at": then,
    }
    assert assess_health(status, settings, now)["healthy"] is healthy


def test_threshold_follows_custom_schedule(settings) -> None:
    now = datetime(2026, 9, 5, tzinfo=UTC)
    then = (now - timedelta(minutes=20)).isoformat()
    status = {
        "version": 1,
        "last_started_at": then,
        "last_completed_at": then,
        "last_rendered_at": then,
    }
    assert assess_health(
        status, replace(settings, airpage_push_interval_minutes=30), now
    )["healthy"]
    assert not assess_health(status, settings, now)["healthy"]


def test_stalled_running_task_is_unhealthy_even_with_recent_output(settings) -> None:
    now = datetime(2026, 9, 5, tzinfo=UTC)
    status = {
        "version": 1,
        "last_started_at": (now - timedelta(minutes=2)).isoformat(),
        "last_completed_at": now.isoformat(),
        "last_rendered_at": now.isoformat(),
        "in_progress": True,
    }
    assert assess_health(status, settings, now)["reason"] == "task_stalled"


@pytest.mark.parametrize(
    "timestamp", ["bad", "2026-09-05T00:00:00", "2100-01-01T00:00:00Z"]
)
def test_invalid_and_future_state_cannot_pass_healthcheck(settings, timestamp) -> None:
    status = {
        "version": 1,
        "last_completed_at": timestamp,
        "last_rendered_at": timestamp,
    }
    assert not assess_health(status, settings, datetime(2026, 9, 5, tzinfo=UTC))[
        "healthy"
    ]


def test_upload_check_can_run_during_the_next_normal_collection(settings) -> None:
    now = datetime(2026, 9, 5, tzinfo=UTC)
    previous = (now - timedelta(seconds=60)).isoformat()
    status = {
        "version": 1,
        "last_started_at": now.isoformat(),
        "last_completed_started_at": previous,
        "last_completed_at": previous,
        "last_rendered_at": previous,
        "last_uploaded_at": previous,
        "in_progress": True,
    }
    assert assess_health(status, settings, now, True)["healthy"]
