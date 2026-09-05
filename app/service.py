from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.airpage import AirPageError, parse_device_url, push_bmp
from app.bmp import encode_gray4_bmp, png_bytes
from app.cache import CacheEntry, Snapshot, SnapshotCache, fingerprint
from app.config import Settings
from app.models import PageData, SnapshotInfo, WeatherSnapshot
from app.providers.news import fetch_news, unavailable_news
from app.providers.stocks import fetch_stock, unavailable_stock
from app.providers.weather import fetch_weather, unavailable_weather
from app.render import render_page
from app.storage import atomic_write, read_json, write_json


def error_name(exc: BaseException) -> str:
    # HTTP exception messages may include the private news URL or device credential.
    return str(exc) if isinstance(exc, AirPageError) else type(exc).__name__


@dataclass(slots=True)
class Source:
    key: str
    fingerprint: str
    refresh: int
    max_age: int
    unavailable: Snapshot
    fetch: Callable[[httpx.AsyncClient], Awaitable[Snapshot]]


class AirPageService:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self.clock = clock or (lambda: datetime.now(UTC))
        self._run_lock = threading.Lock()
        self.cache = SnapshotCache(settings.output_dir / "cache.json")
        try:
            status = read_json(self.status_path)
            self.status = (
                status
                if isinstance(status, dict) and status.get("version") == 1
                else {}
            )
        except (OSError, ValueError):
            self.status = {}

    @property
    def png_path(self) -> Path:
        return self.settings.output_dir / "airpage.png"

    @property
    def bmp_path(self) -> Path:
        return self.settings.output_dir / "airpage.bmp"

    @property
    def status_path(self) -> Path:
        return self.settings.output_dir / "status.json"

    def start_worker(self) -> None:
        # A persistent volume must not make a newly started worker look successful.
        self.status = {"version": 1, "worker_started_at": self.clock().isoformat()}
        self._write_status()

    def _write_status(self) -> None:
        write_json(self.status_path, self.status)

    def _sources(self) -> list[Source]:
        s = self.settings
        sources = [
            Source(
                "weather",
                fingerprint(
                    s.weather_latitude,
                    s.weather_longitude,
                    s.weather_timezone,
                    s.weather_location,
                    s.weather_forecast_days,
                ),
                s.weather_refresh_seconds,
                s.weather_max_age_seconds,
                unavailable_weather(s),
                partial(fetch_weather, s),
            )
        ]
        for position, (symbol, label) in enumerate(
            zip(s.stock_symbols, s.stock_labels, strict=True)
        ):
            sources.append(
                Source(
                    f"stock:{position}:{symbol}",
                    fingerprint(symbol, label, s.stock_range, s.stock_interval),
                    s.stock_refresh_seconds,
                    s.stock_max_age_seconds,
                    unavailable_stock(symbol, label),
                    partial(fetch_stock, s, symbol=symbol, label=label),
                )
            )
        if s.news_api_base_url:
            sources.append(
                Source(
                    "news",
                    fingerprint(
                        s.news_api_base_url, s.news_category, s.news_items, s.news_label
                    ),
                    s.news_refresh_seconds,
                    s.news_max_age_seconds,
                    unavailable_news(s),
                    partial(fetch_news, s),
                )
            )
        return sources

    def _due(self, source: Source, entry: CacheEntry, now: datetime) -> bool:
        if entry.last_attempt_at is None or entry.last_attempt_at > now:
            return True
        if (
            entry.snapshot
            and entry.snapshot.info.fetched_at
            and entry.snapshot.info.fetched_at > now
        ):
            return True
        delay = min(source.refresh, source.max_age)
        if entry.failures:
            delay = min(300, 15 * 2 ** min(entry.failures, 5))
            return (now - entry.last_attempt_at).total_seconds() >= delay
        elif isinstance(entry.snapshot, WeatherSnapshot):
            fetched = entry.snapshot.info.fetched_at
            zone = ZoneInfo(self.settings.weather_timezone)
            if (
                fetched is None
                or fetched.astimezone(zone).date() != now.astimezone(zone).date()
            ):
                return True
        # Scheduler/client startup jitter must not turn a 60-second source into a
        # 120-second source. Successful polls run once per wall-clock time window.
        return int(now.timestamp() // delay) > int(
            entry.last_attempt_at.timestamp() // delay
        )

    def _view(self, source: Source, entry: CacheEntry, now: datetime) -> Snapshot:
        snapshot = entry.snapshot
        if snapshot is None or snapshot.info.fetched_at is None:
            return replace(source.unavailable, info=SnapshotInfo(error=entry.error))
        age = (now - snapshot.info.fetched_at).total_seconds()
        if not 0 <= age <= source.max_age:
            return replace(
                source.unavailable,
                info=replace(snapshot.info, state="unavailable", error="cache_expired"),
            )
        info = replace(
            snapshot.info,
            state="stale" if entry.error or snapshot.info.state == "stale" else "fresh",
            error=entry.error,
        )
        if isinstance(snapshot, WeatherSnapshot):
            today = now.astimezone(ZoneInfo(self.settings.weather_timezone)).date()
            days = sorted(
                (
                    day
                    for day in snapshot.forecasts
                    if today
                    <= day.date
                    < today + timedelta(days=self.settings.weather_forecast_days)
                ),
                key=lambda day: day.date,
            )
            if not days:
                return replace(
                    source.unavailable,
                    info=replace(info, state="unavailable", error="forecast_expired"),
                )
            return replace(snapshot, forecasts=days, info=info)
        return replace(snapshot, info=info)

    async def _fetch(self, source: Source, client: httpx.AsyncClient) -> Snapshot:
        snapshot = await source.fetch(client)
        if not snapshot.available:
            raise ValueError("provider has no usable data")
        snapshot.info = replace(snapshot.info, fetched_at=self.clock(), error=None)
        return snapshot

    async def collect(self, client: httpx.AsyncClient) -> PageData:
        now = self.clock()
        sources = self._sources()
        keys = {source.key for source in sources}
        self.cache.entries = {
            key: entry for key, entry in self.cache.entries.items() if key in keys
        }
        tasks: dict[asyncio.Task[Snapshot], CacheEntry] = {}
        for source in sources:
            entry = self.cache.entries.get(source.key)
            if entry is None or entry.fingerprint != source.fingerprint:
                entry = self.cache.entries[source.key] = CacheEntry(source.fingerprint)
            if self._due(source, entry, now):
                entry.last_attempt_at = now
                tasks[asyncio.create_task(self._fetch(source, client))] = entry
        if tasks:
            done, pending = await asyncio.wait(
                tasks, timeout=self.settings.collection_timeout_seconds
            )
            for task in pending:
                task.cancel()
                entry = tasks[task]
                entry.failures += 1
                entry.error = "TimeoutError"
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                entry = tasks[task]
                try:
                    snapshot = task.result()
                    entry.snapshot, entry.failures, entry.error = snapshot, 0, None
                except Exception as exc:  # noqa: BLE001 - isolate each provider
                    entry.failures += 1
                    entry.error = type(exc).__name__
        self.cache.save()
        now = self.clock()
        snapshots = {
            source.key: self._view(source, self.cache.entries[source.key], now)
            for source in sources
        }
        self.status["sources"] = {
            key: {
                **asdict(snapshot.info),
                "consecutive_failures": self.cache.entries[key].failures,
            }
            for key, snapshot in snapshots.items()
        }
        self.status["sources"] = json.loads(
            json.dumps(self.status["sources"], default=lambda value: value.isoformat())
        )
        self.status["degraded"] = any(
            snapshot.info.state != "fresh" for snapshot in snapshots.values()
        )
        return PageData(
            now=now.astimezone(ZoneInfo(self.settings.timezone)),
            weather=snapshots["weather"],
            stocks=[
                snapshots[f"stock:{position}:{symbol}"]
                for position, symbol in enumerate(self.settings.stock_symbols)
            ],
            news=snapshots.get("news", unavailable_news(self.settings)),
        )

    async def _run(self, push: bool, demo: bool) -> dict[str, Any]:
        async with httpx.AsyncClient(
            timeout=self.settings.request_timeout_seconds,
            follow_redirects=True,
            transport=self.transport,
            limits=httpx.Limits(max_connections=5),
            headers={"Accept": "application/json"},
        ) as client:
            if demo:
                from app.demo import demo_page

                data = demo_page(self.settings, self.clock())
            else:
                data = await self.collect(client)
            image = render_page(data, self.settings)
            png, bmp = png_bytes(image), encode_gray4_bmp(image)
            if len(bmp) > 512 * 1024:
                raise RuntimeError("BMP 超过 512 KiB")
            atomic_write(self.png_path, png)
            atomic_write(self.bmp_path, bmp)
            self.status["last_rendered_at"] = self.clock().isoformat()
            self._write_status()
            outcome: dict[str, Any] = {
                "ok": True,
                "rendered": True,
                "pushed": False,
                "uploaded": False,
                "refresh_requested": False,
                "display_updated": None,
                "timestamp": data.now.isoformat(),
                "png": str(self.png_path),
                "bmp": str(self.bmp_path),
                "bmp_bytes": len(bmp),
                "weather_available": data.weather.available,
                "stocks_available": sum(stock.available for stock in data.stocks),
                "news_available": data.news.available,
                "news_items": len(data.news.items),
                "degraded": self.status.get("degraded", False),
                "source_states": {
                    key: value["state"]
                    for key, value in self.status.get("sources", {}).items()
                },
                "demo": demo,
            }
            if push:
                if (
                    not self.settings.airpage_enabled
                    or not self.settings.airpage_device_url
                ):
                    raise AirPageError("推送未启用或尚未设置设备链接")
                device = parse_device_url(
                    self.settings.airpage_device_url,
                    self.settings.airpage_trusted_hosts,
                )
                if (device.width, device.height) != (
                    self.settings.width,
                    self.settings.height,
                ):
                    raise AirPageError("设备尺寸与渲染配置不一致")
                try:
                    result = await asyncio.wait_for(
                        push_bmp(client, device, bmp),
                        self.settings.push_timeout_seconds,
                    )
                except Exception:
                    self.status["consecutive_upload_failures"] = (
                        self.status.get("consecutive_upload_failures", 0) + 1
                    )
                    raise
                self.status.update(
                    last_uploaded_at=self.clock().isoformat(),
                    consecutive_upload_failures=0,
                    manual_refresh=result["manual_refresh"],
                )
                if result["refresh_requested"]:
                    self.status["last_refresh_requested_at"] = self.clock().isoformat()
                else:
                    self.status["degraded"] = True
                outcome.update(
                    pushed=True,
                    uploaded=True,
                    refresh_requested=result["refresh_requested"],
                    push=result,
                    degraded=self.status.get("degraded", False),
                )
            return outcome

    def run_once(self, push: bool = False, *, demo: bool = False) -> dict[str, Any]:
        if demo and push:
            raise ValueError("演示数据仅用于离线预览")
        if not self._run_lock.acquire(blocking=False):
            raise RuntimeError("已有一次渲染或推送正在执行")
        try:
            self.status.update(
                version=1,
                last_started_at=self.clock().isoformat(),
                in_progress=True,
                last_error=None,
            )
            self._write_status()
            try:
                result = asyncio.run(self._run(push, demo))
                self.status["consecutive_run_failures"] = 0
                return result
            except Exception as exc:
                self.status.update(
                    last_error=error_name(exc),
                    degraded=True,
                    consecutive_run_failures=self.status.get(
                        "consecutive_run_failures", 0
                    )
                    + 1,
                )
                raise
            finally:
                self.status.update(
                    last_completed_at=self.clock().isoformat(),
                    in_progress=False,
                    last_completed_started_at=self.status["last_started_at"],
                )
                self._write_status()
        finally:
            self._run_lock.release()

    def safe_scheduled_run(self) -> None:
        try:
            result = self.run_once(
                push=bool(
                    self.settings.airpage_enabled and self.settings.airpage_device_url
                )
            )
            print(json.dumps({"event": "scheduled_run", **result}, ensure_ascii=False))
        except Exception as exc:  # noqa: BLE001 - scheduler must survive a failed run
            print(
                json.dumps(
                    {"event": "scheduled_run_failed", "error": error_name(exc)},
                    ensure_ascii=False,
                )
            )
