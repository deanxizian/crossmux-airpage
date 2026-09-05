from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import Settings
from app.storage import read_json
from app.validation import timestamp


def assess_health(
    status: dict[str, Any],
    settings: Settings,
    now: datetime,
    require_upload: bool = False,
) -> dict[str, object]:
    budget = settings.collection_timeout_seconds + settings.push_timeout_seconds + 30
    threshold = max(120, 2 * settings.airpage_push_interval_minutes * 60 + budget)
    try:
        if status.get("version") != 1:
            raise ValueError("unknown status version")
        completed = timestamp(status.get("last_completed_at"))
        rendered = timestamp(status.get("last_rendered_at"))
        started = timestamp(status.get("last_started_at"))
        for value in (completed, rendered, started):
            if value is not None and value > now:
                raise ValueError("status timestamp is in the future")
        if (
            status.get("in_progress")
            and started
            and (now - started).total_seconds() > budget
        ):
            return {"healthy": False, "reason": "task_stalled"}
        if completed is None or (now - completed).total_seconds() > threshold:
            return {"healthy": False, "reason": "task_not_completed_recently"}
        if rendered is None or (now - rendered).total_seconds() > threshold:
            return {"healthy": False, "reason": "render_not_completed_recently"}
        if require_upload:
            uploaded = timestamp(status.get("last_uploaded_at"))
            completed_started = (
                timestamp(status.get("last_completed_started_at")) or started
            )
            if (
                uploaded is None
                or completed_started is None
                or uploaded < completed_started
                or uploaded > now
                or status.get("consecutive_upload_failures", 0)
            ):
                return {"healthy": False, "reason": "latest_upload_not_confirmed"}
        return {
            "healthy": True,
            "degraded": bool(status.get("degraded", False)),
            "reason": "scheduler_running",
        }
    except (TypeError, ValueError, OverflowError):
        return {"healthy": False, "reason": "invalid_status"}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check task freshness without external requests"
    )
    parser.add_argument("--require-upload", action="store_true")
    args = parser.parse_args()
    settings = Settings.from_env()
    try:
        status = read_json(Path(settings.output_dir) / "status.json")
        if not isinstance(status, dict):
            raise ValueError("invalid status")
        result = assess_health(status, settings, datetime.now(UTC), args.require_upload)
    except (OSError, ValueError):
        result = {"healthy": False, "reason": "status_unavailable"}
    print(json.dumps(result))
    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
