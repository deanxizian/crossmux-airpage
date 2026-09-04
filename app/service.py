from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.airpage import AirPageError, parse_device_url, push_bmp
from app.bmp import encode_gray4_bmp, png_bytes
from app.config import Settings
from app.models import NewsSnapshot, PageData, StockSnapshot, WeatherSnapshot
from app.providers.news import fetch_news, unavailable_news
from app.providers.stocks import fetch_stock, unavailable_stock
from app.providers.weather import fetch_weather, unavailable_weather
from app.render import render_page

PROVIDER_ERRORS = (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError)


class AirPageService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = httpx.Client(
            timeout=settings.request_timeout_seconds,
            follow_redirects=True,
            headers={"Accept": "application/json"},
        )
        self._run_lock = threading.Lock()
        self._weather_cache: WeatherSnapshot | None = None
        self._stock_cache: dict[str, StockSnapshot] = {}
        self._news_cache: NewsSnapshot | None = None

    @property
    def png_path(self) -> Path:
        return self.settings.output_dir / "airpage.png"

    @property
    def bmp_path(self) -> Path:
        return self.settings.output_dir / "airpage.bmp"

    def close(self) -> None:
        self.client.close()

    def collect(self, now: datetime) -> PageData:
        try:
            weather = fetch_weather(self.settings, self.client)
            self._weather_cache = weather
        except PROVIDER_ERRORS:
            weather = self._weather_cache or unavailable_weather(self.settings)

        stocks: list[StockSnapshot] = []
        for symbol, label in zip(
            self.settings.stock_symbols, self.settings.stock_labels, strict=True
        ):
            try:
                stock = fetch_stock(self.settings, self.client, symbol, label)
                self._stock_cache[symbol] = stock
            except PROVIDER_ERRORS:
                stock = self._stock_cache.get(symbol) or unavailable_stock(
                    symbol, label
                )
            stocks.append(stock)

        try:
            news = fetch_news(self.settings, self.client)
            self._news_cache = news
        except PROVIDER_ERRORS:
            news = self._news_cache or unavailable_news(self.settings)

        return PageData(now=now, weather=weather, stocks=stocks, news=news)

    @staticmethod
    def _atomic_write(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(content)
        temporary.replace(path)

    def run_once(self, push: bool = False) -> dict[str, Any]:
        if not self._run_lock.acquire(blocking=False):
            raise RuntimeError("已有一次渲染或推送正在执行")
        try:
            now = datetime.now(ZoneInfo(self.settings.timezone))
            data = self.collect(now)
            image = render_page(data, self.settings)
            png = png_bytes(image)
            bmp = encode_gray4_bmp(image)
            if len(bmp) > 512 * 1024:
                raise RuntimeError(f"BMP 大小 {len(bmp)} bytes 超过 512 KiB")
            self._atomic_write(self.png_path, png)
            self._atomic_write(self.bmp_path, bmp)

            outcome: dict[str, Any] = {
                "ok": True,
                "rendered": True,
                "pushed": False,
                "timestamp": now.isoformat(),
                "png": str(self.png_path),
                "bmp": str(self.bmp_path),
                "bmp_bytes": len(bmp),
                "weather_available": data.weather.available,
                "stocks_available": sum(1 for stock in data.stocks if stock.available),
                "news_available": data.news.available,
                "news_items": len(data.news.items),
            }
            if push:
                if not self.settings.airpage_enabled:
                    raise AirPageError("AIRPAGE_ENABLED=false，已跳过推送")
                if not self.settings.airpage_device_url:
                    raise AirPageError("尚未设置 AIRPAGE_DEVICE_URL")
                device = parse_device_url(
                    self.settings.airpage_device_url,
                    self.settings.airpage_trusted_hosts,
                )
                if (device.width, device.height) != (
                    self.settings.width,
                    self.settings.height,
                ):
                    raise AirPageError(
                        f"设备为 {device.width}x{device.height}，渲染配置为 "
                        f"{self.settings.width}x{self.settings.height}"
                    )
                push_result = push_bmp(self.client, device, bmp)
                outcome.update({"pushed": True, "push": push_result})
            return outcome
        finally:
            self._run_lock.release()

    def safe_scheduled_run(self) -> None:
        should_push = bool(
            self.settings.airpage_enabled and self.settings.airpage_device_url
        )
        try:
            result = self.run_once(push=should_push)
            print(json.dumps({"event": "scheduled_run", **result}, ensure_ascii=False))
        except Exception as exc:  # noqa: BLE001 - scheduler must survive a failed run
            print(
                json.dumps(
                    {"event": "scheduled_run_failed", "error": str(exc)},
                    ensure_ascii=False,
                )
            )
