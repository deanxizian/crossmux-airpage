from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.worker import main


@pytest.mark.parametrize("on_start", [True, False])
def test_worker_initializes_status_and_uses_configured_non_overlapping_schedule(
    settings, monkeypatch, on_start
) -> None:
    from dataclasses import replace

    settings = replace(
        settings, airpage_push_interval_minutes=3, airpage_push_on_start=on_start
    )
    service, scheduler = Mock(), Mock()
    monkeypatch.setattr("app.worker.Settings.from_env", lambda: settings)
    monkeypatch.setattr("app.worker.AirPageService", lambda _: service)
    monkeypatch.setattr("app.worker.BlockingScheduler", lambda **_: scheduler)
    assert main() == 0
    service.start_worker.assert_called_once()
    assert service.safe_scheduled_run.call_count == int(on_start)
    options = scheduler.add_job.call_args.kwargs
    assert (
        options["minutes"] == 3
        and options["max_instances"] == 1
        and options["coalesce"]
    )
    scheduler.start.assert_called_once()
