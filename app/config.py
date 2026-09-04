from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_TRUSTED_HOSTS = (
    "airpage.crossmux.cn",
    "airpage.crossmux.com",
    "airpage.yunhug.com",
)
DEFAULT_NEWS_API_BASE_URL = ""
DEFAULT_WEATHER_LOCATION = "上海"
DEFAULT_WEATHER_LATITUDE = 31.2304
DEFAULT_WEATHER_LONGITUDE = 121.4737
DEFAULT_STOCK_SYMBOLS = ("601727.SS", "600021.SS")
DEFAULT_STOCK_LABELS = ("上海电气", "上海电力")


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(value: str | None, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except ValueError:
        parsed = default
    return max(minimum, min(maximum, parsed))


def _float(value: str | None, default: float) -> float:
    try:
        return float(value) if value is not None else default
    except ValueError:
        return default


def _csv(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        return default
    parsed = tuple(item.strip() for item in value.split(",") if item.strip())
    return parsed or default


@dataclass(frozen=True, slots=True)
class Settings:
    timezone: str
    width: int
    height: int
    output_dir: Path
    weather_location: str
    weather_latitude: float
    weather_longitude: float
    weather_timezone: str
    weather_forecast_days: int
    stock_symbols: tuple[str, ...]
    stock_labels: tuple[str, ...]
    stock_range: str
    stock_interval: str
    news_api_base_url: str | None
    news_category: str
    news_label: str
    news_items: int
    airpage_device_url: str | None
    airpage_enabled: bool
    airpage_push_interval_minutes: int
    airpage_push_on_start: bool
    airpage_trusted_hosts: tuple[str, ...]
    request_timeout_seconds: float
    font_sans_path: str | None
    font_mono_path: str | None

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        if environ is None:
            load_dotenv(override=False)
            env: Mapping[str, str] = os.environ
        else:
            env = environ
        index_symbol = (
            env.get("MARKET_INDEX_SYMBOL", "000001.SS").strip() or "000001.SS"
        )
        index_label = env.get("MARKET_INDEX_LABEL", "上证指数").strip() or "上证指数"
        watch_symbols = _csv(env.get("STOCK_SYMBOLS"), DEFAULT_STOCK_SYMBOLS)[:2]
        watch_labels = _csv(env.get("STOCK_LABELS"), DEFAULT_STOCK_LABELS)
        if len(watch_labels) < len(watch_symbols):
            watch_labels = watch_labels + watch_symbols[len(watch_labels) :]
        symbols = (index_symbol, *watch_symbols)
        labels = (index_label, *watch_labels[: len(watch_symbols)])
        return cls(
            timezone=env.get("TZ", "Asia/Shanghai"),
            width=_int(env.get("AIRPAGE_WIDTH"), 528, 128, 1600),
            height=_int(env.get("AIRPAGE_HEIGHT"), 792, 128, 1600),
            output_dir=Path(env.get("OUTPUT_DIR", "data")),
            weather_location=env.get(
                "WEATHER_LOCATION", DEFAULT_WEATHER_LOCATION
            ).strip()
            or DEFAULT_WEATHER_LOCATION,
            weather_latitude=_float(
                env.get("WEATHER_LATITUDE"), DEFAULT_WEATHER_LATITUDE
            ),
            weather_longitude=_float(
                env.get("WEATHER_LONGITUDE"), DEFAULT_WEATHER_LONGITUDE
            ),
            weather_timezone=env.get(
                "WEATHER_TIMEZONE", env.get("TZ", "Asia/Shanghai")
            ),
            weather_forecast_days=_int(env.get("WEATHER_FORECAST_DAYS"), 5, 1, 5),
            stock_symbols=symbols,
            stock_labels=labels,
            stock_range=env.get("STOCK_RANGE", "5d"),
            stock_interval=env.get("STOCK_INTERVAL", "30m"),
            news_api_base_url=(
                env.get("NEWS_API_BASE_URL", DEFAULT_NEWS_API_BASE_URL).strip() or None
            ),
            news_category=env.get("NEWS_CATEGORY", "all").strip() or "all",
            news_label=env.get("NEWS_LABEL", "新浪 · 快讯").strip() or "新浪 · 快讯",
            news_items=_int(env.get("NEWS_ITEMS"), 4, 1, 4),
            airpage_device_url=env.get("AIRPAGE_DEVICE_URL") or None,
            airpage_enabled=_bool(env.get("AIRPAGE_ENABLED"), True),
            airpage_push_interval_minutes=_int(
                env.get("AIRPAGE_PUSH_INTERVAL_MINUTES"), 1, 1, 1440
            ),
            airpage_push_on_start=_bool(env.get("AIRPAGE_PUSH_ON_START"), True),
            airpage_trusted_hosts=_csv(
                env.get("AIRPAGE_TRUSTED_HOSTS"), DEFAULT_TRUSTED_HOSTS
            ),
            request_timeout_seconds=_float(env.get("REQUEST_TIMEOUT_SECONDS"), 20.0),
            font_sans_path=env.get("FONT_SANS_PATH") or None,
            font_mono_path=env.get("FONT_MONO_PATH") or None,
        )
