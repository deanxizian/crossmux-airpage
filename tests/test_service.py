from __future__ import annotations

import asyncio
import json
import time
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import httpx
import pytest

from app.config import Settings
from app.healthcheck import assess_health
from app.service import AirPageService


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 5, 1, tzinfo=UTC)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


class API:
    def __init__(self, clock) -> None:
        self.clock = clock
        self.calls = Counter()
        self.failed = False
        self.bad_weather = False
        self.business_failure = False
        self.refreshed = True

    async def __call__(self, request):
        kind = (
            "push"
            if request.method == "POST"
            else "weather"
            if request.url.host == "api.open-meteo.com"
            else "stock"
            if request.url.host == "query2.finance.yahoo.com"
            else "news"
        )
        self.calls[kind] += 1
        if self.failed and kind != "push":
            raise httpx.ConnectError(
                "private endpoint must not appear in logs", request=request
            )
        if kind == "push":
            return httpx.Response(
                200,
                json={
                    "ok": not self.business_failure,
                    "bytes": 104614,
                    "refreshed": self.refreshed,
                },
            )
        if kind == "weather":
            today = (self.clock() + timedelta(hours=8)).date()
            return httpx.Response(
                200,
                json={
                    "daily": {
                        "time": [
                            (today + timedelta(days=i)).isoformat() for i in range(5)
                        ],
                        "weather_code": [2] * 5,
                        "temperature_2m_max": ["bad" if self.bad_weather else 31] * 5,
                        "temperature_2m_min": [24] * 5,
                        "precipitation_probability_max": [20] * 5,
                    }
                },
            )
        if kind == "stock":
            return httpx.Response(
                200,
                json={
                    "chart": {
                        "result": [
                            {
                                "meta": {
                                    "regularMarketPrice": 100,
                                    "previousClose": 99,
                                    "regularMarketTime": self.clock().timestamp(),
                                },
                                "indicators": {"quote": [{"close": [99, 100]}]},
                            }
                        ]
                    }
                },
            )
        return httpx.Response(
            200,
            json={
                "stale": False,
                "items": [
                    {"content": "测试快讯", "published_at": self.clock().isoformat()}
                ],
            },
        )


@pytest.fixture
def setup(tmp_path):
    clock = Clock()
    api = API(clock)
    settings = Settings.from_env(
        {
            "OUTPUT_DIR": str(tmp_path),
            "NEWS_API_BASE_URL": "https://news.example.invalid/secret-test-token",
            "AIRPAGE_DEVICE_URL": "https://airpage.example.invalid/?id=0123456789abcdef&w=528&h=792&mode=gray4",
            "AIRPAGE_TRUSTED_HOSTS": "airpage.example.invalid",
        }
    )
    service = AirPageService(settings, clock=clock, transport=httpx.MockTransport(api))
    return service, api, clock


def collect(service):
    async def run():
        async with httpx.AsyncClient(transport=service.transport) as client:
            return await service.collect(client)

    return asyncio.run(run())


def test_fetch_periods_are_independent_and_clock_keeps_advancing(setup) -> None:
    service, api, clock = setup
    collect(service)
    assert api.calls == {"weather": 1, "stock": 3, "news": 1}
    clock.advance(60)
    page = collect(service)
    assert api.calls == {"weather": 1, "stock": 6, "news": 1}
    assert page.now.timestamp() == clock().timestamp()
    clock.advance(60)
    collect(service)
    assert api.calls == {"weather": 1, "stock": 9, "news": 2}


def test_stale_cache_expires_and_recovers(setup) -> None:
    service, api, clock = setup
    service.settings = replace(
        service.settings,
        weather_refresh_seconds=60,
        news_refresh_seconds=60,
        weather_max_age_seconds=120,
        stock_max_age_seconds=120,
        news_max_age_seconds=120,
    )
    collect(service)
    clock.advance(61)
    api.failed = True
    stale = collect(service)
    assert stale.weather.available and stale.weather.info.state == "stale"
    assert all(stock.info.state == "stale" for stock in stale.stocks)
    assert stale.news.info.state == "stale"
    calls = api.calls.copy()
    clock.advance(1)
    collect(service)
    assert (
        api.calls == calls
    )  # failed sources back off rather than immediately retrying
    clock.advance(60)
    expired = collect(service)
    assert not expired.weather.available and expired.weather.forecasts == []
    assert all(not stock.available for stock in expired.stocks)
    assert not expired.news.available and expired.news.items == []
    clock.advance(61)
    api.failed = False
    fresh = collect(service)
    assert fresh.weather.info.state == "fresh" and fresh.news.info.state == "fresh"


def test_restart_recovers_cache_without_persisting_credentials(setup) -> None:
    service, api, clock = setup
    collect(service)
    contents = service.cache.path.read_text()
    assert "https://" not in contents and "secret-test-token" not in contents
    assert "0123456789abcdef" not in contents
    restarted = AirPageService(
        service.settings, clock=clock, transport=service.transport
    )
    api.failed = True
    clock.advance(61)
    page = collect(restarted)
    assert page.weather.available and page.stocks[0].info.state == "stale"
    assert page.news.items[0].published_at is not None
    assert service.cache.path.stat().st_mode & 0o777 == 0o600


def test_configuration_change_never_reuses_the_other_feed(setup) -> None:
    service, api, clock = setup
    collect(service)
    settings = replace(
        service.settings,
        news_api_base_url="https://news.example.invalid/different-feed",
    )
    changed = AirPageService(settings, clock=clock, transport=service.transport)
    api.failed = True
    page = collect(changed)
    assert not page.news.available
    assert page.weather.available


def test_weather_crosses_midnight_without_showing_yesterday(setup) -> None:
    service, api, clock = setup
    clock.now = datetime(2026, 9, 5, 15, 59, 50, tzinfo=UTC)
    first = collect(service)
    yesterday = first.weather.forecasts[0].date
    api.failed = True
    clock.advance(20)
    page = collect(service)
    assert api.calls["weather"] == 2
    assert page.weather.info.state == "stale"
    assert all(day.date > yesterday for day in page.weather.forecasts)


def test_bad_weather_cannot_poison_a_valid_cache_or_break_the_page(setup) -> None:
    service, api, clock = setup
    service.settings = replace(service.settings, weather_refresh_seconds=60)
    collect(service)
    clock.advance(61)
    api.bad_weather = True
    result = service.run_once()
    assert result["rendered"] and result["degraded"]
    assert service.cache.entries["weather"].snapshot.forecasts[0].high == 31
    assert service.status["sources"]["weather"]["state"] == "stale"


def test_first_failure_still_renders_an_unavailable_module(setup) -> None:
    service, api, _ = setup
    api.bad_weather = True
    result = service.run_once()
    assert result["rendered"] and not result["weather_available"]
    assert result["stocks_available"] == 3


def test_collection_deadline_cancels_slow_source_and_keeps_fast_results(setup) -> None:
    service, api, _ = setup
    cancelled = []

    async def slow_api(request):
        if request.url.host == "api.open-meteo.com":
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(True)
        return await api(request)

    service.transport = httpx.MockTransport(slow_api)
    service.settings = replace(service.settings, collection_timeout_seconds=0.03)
    started = time.monotonic()
    page = collect(service)
    assert time.monotonic() - started < 1
    assert cancelled and not page.weather.available
    assert all(stock.available for stock in page.stocks) and page.news.available


def test_clock_is_captured_after_collection(setup) -> None:
    service, api, clock = setup

    async def slow_api(request):
        if request.url.host == "api.open-meteo.com":
            clock.advance(15)
        return await api(request)

    service.transport = httpx.MockTransport(slow_api)
    result = service.run_once()
    assert (
        datetime.fromisoformat(result["timestamp"]).timestamp() == clock().timestamp()
    )


def test_business_failure_fails_cli_and_records_degradation(
    setup, monkeypatch, capsys
) -> None:
    from app.cli import main

    service, api, clock = setup
    api.business_failure = True
    monkeypatch.setattr("app.cli.AirPageService", lambda _: service)
    monkeypatch.setattr("app.cli.Settings.from_env", lambda: service.settings)
    monkeypatch.setattr("sys.argv", ["app", "--push", "--json"])
    assert main() == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False
    status = json.loads(service.status_path.read_text())
    assert status["consecutive_upload_failures"] == 1
    assert "last_uploaded_at" not in status
    assert assess_health(status, service.settings, clock())["healthy"]
    assert not assess_health(status, service.settings, clock(), True)["healthy"]


def test_success_and_partial_refresh_have_honest_status(setup) -> None:
    service, api, clock = setup
    result = service.run_once(push=True)
    assert result["uploaded"] and result["refresh_requested"]
    assert result["display_updated"] is None
    assert assess_health(service.status, service.settings, clock(), True)["healthy"]
    clock.advance(60)
    api.refreshed = False
    result = service.run_once(push=True)
    assert result["uploaded"] and not result["refresh_requested"]
    assert result["push"]["manual_refresh"] and result["degraded"]
    assert (
        api.calls["push"] == 2
    )  # no immediate re-upload after failed refresh notification


def test_stuck_push_has_a_total_deadline(setup) -> None:
    service, api, _ = setup

    async def slow_api(request):
        if request.method == "POST":
            await asyncio.Event().wait()
        return await api(request)

    service.transport = httpx.MockTransport(slow_api)
    service.settings = replace(service.settings, push_timeout_seconds=0.03)
    with pytest.raises(TimeoutError):
        service.run_once(push=True)
    assert service.status["consecutive_upload_failures"] == 1
    assert service.status["last_completed_at"] and not service.status["in_progress"]


def test_corrupt_cache_is_ignored_per_source(setup) -> None:
    service, api, clock = setup
    collect(service)
    payload = json.loads(service.cache.path.read_text())
    payload["entries"]["weather"]["snapshot"]["forecasts"][0]["high"] = "bad"
    service.cache.path.write_text(json.dumps(payload))
    restarted = AirPageService(
        service.settings, clock=clock, transport=service.transport
    )
    api.failed = True
    page = collect(restarted)
    assert not page.weather.available and all(stock.available for stock in page.stocks)


def test_worker_restart_resets_old_success_status(setup) -> None:
    service, _, clock = setup
    service.run_once(push=True)
    service.start_worker()
    assert not assess_health(service.status, service.settings, clock())["healthy"]


def test_demo_uses_no_network_and_cannot_be_pushed(setup) -> None:
    service, api, _ = setup
    result = service.run_once(demo=True)
    assert result["demo"] and result["bmp_bytes"] == 104614 and api.calls == {}
    with pytest.raises(ValueError):
        service.run_once(push=True, demo=True)


def test_failed_run_releases_lock_and_scheduler_sanitizes_errors(setup, capsys) -> None:
    service, _, _ = setup
    with patch(
        "app.service.render_page",
        side_effect=RuntimeError("https://private.example/secret"),
    ):
        service.safe_scheduled_run()
    assert "private.example" not in capsys.readouterr().out
    assert service.run_once()["ok"]


def test_repeated_symbols_keep_each_rows_explicit_name(setup) -> None:
    service, _, _ = setup
    service.settings = replace(
        service.settings,
        stock_symbols=("000001.SS", "000001.SS"),
        stock_labels=("指数", "同代码自选"),
    )
    page = collect(service)
    assert [stock.label for stock in page.stocks] == ["指数", "同代码自选"]


def test_poll_windows_tolerate_scheduler_startup_jitter(setup) -> None:
    service, api, clock = setup
    clock.advance(0.8)
    collect(service)
    clock.advance(59.4)  # next minute, slightly less than 60 seconds since first fetch
    collect(service)
    assert api.calls == {"weather": 1, "stock": 6, "news": 1}
    clock.advance(0.1)
    collect(service)
    assert api.calls == {"weather": 1, "stock": 6, "news": 1}
    clock.advance(59.9)
    collect(service)
    assert api.calls == {"weather": 1, "stock": 9, "news": 2}
