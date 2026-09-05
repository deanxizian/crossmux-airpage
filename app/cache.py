from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.models import (
    ForecastDay,
    NewsItem,
    NewsSnapshot,
    SnapshotInfo,
    StockSnapshot,
    WeatherSnapshot,
)
from app.storage import read_json, write_json
from app.validation import integer, number, timestamp

Snapshot = WeatherSnapshot | StockSnapshot | NewsSnapshot


def fingerprint(*values: object) -> str:
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()


@dataclass(slots=True)
class CacheEntry:
    fingerprint: str
    snapshot: Snapshot | None = None
    last_attempt_at: datetime | None = None
    failures: int = 0
    error: str | None = None


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("cached text must be a string")
    return value


def _decode_snapshot(kind: str, value: dict[str, Any]) -> Snapshot:
    raw_info = value["info"]
    state = raw_info["state"]
    if state not in {"fresh", "stale"}:
        raise ValueError("invalid cached state")
    info = SnapshotInfo(
        timestamp(raw_info["fetched_at"]), timestamp(raw_info["data_at"]), state
    )
    if info.fetched_at is None or value.get("available") is not True:
        raise ValueError("cache has no successful fetch")
    if kind == "weather":
        forecasts = [
            ForecastDay(
                date.fromisoformat(item["date"]),
                number(item["high"]),
                number(item["low"]),
                integer(item["precipitation_probability"], 0, 100),
                integer(item["weather_code"], 0, 99),
                _text(item["description"]),
            )
            for item in value["forecasts"][:5]
        ]
        if not forecasts or any(
            day.high is not None and day.low is not None and day.high < day.low
            for day in forecasts
        ):
            raise ValueError("invalid cached forecast")
        return WeatherSnapshot(_text(value["location"]), forecasts, True, info)
    if kind == "news":
        items = [
            NewsItem(_text(item["title"]), timestamp(item.get("published_at")))
            for item in value["items"][:4]
        ]
        if not items or any(not item.title.strip() for item in items):
            raise ValueError("invalid cached news")
        return NewsSnapshot(_text(value["label"]), items, True, info)
    if kind == "stock":
        points = [
            point for raw in value["points"][-40:] if (point := number(raw)) is not None
        ]
        price = number(value["price"])
        if price is None and not points:
            raise ValueError("invalid cached price")
        return StockSnapshot(
            _text(value["symbol"]),
            _text(value["label"]),
            price,
            number(value["change_percent"]),
            points,
            True,
            info,
        )
    raise ValueError("unknown snapshot kind")


class SnapshotCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries: dict[str, CacheEntry] = {}
        try:
            payload = read_json(path)
            if not isinstance(payload, dict) or payload.get("version") != 1:
                return
            for key, raw in payload["entries"].items():
                try:
                    snapshot = (
                        _decode_snapshot(key.split(":", 1)[0], raw["snapshot"])
                        if raw["snapshot"]
                        else None
                    )
                    self.entries[key] = CacheEntry(
                        _text(raw["fingerprint"]),
                        snapshot,
                        timestamp(raw["last_attempt_at"]),
                        integer(raw["failures"], 0, 1000000) or 0,
                        _text(raw["error"]) if raw.get("error") else None,
                    )
                except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
                    continue
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            pass

    def save(self) -> None:
        # Serialize only normalized public data; URL credentials never enter the file.
        encoded = json.loads(
            json.dumps(
                {key: asdict(entry) for key, entry in self.entries.items()},
                default=lambda value: value.isoformat(),
                allow_nan=False,
            )
        )
        write_json(self.path, {"version": 1, "entries": encoded})
