from __future__ import annotations

import math
from datetime import UTC, datetime


def number(value: object) -> float | None:
    """Validate JSON numbers before they reach a renderer or durable cache."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("expected a JSON number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("number must be finite")
    return result


def integer(value: object, minimum: int, maximum: int) -> int | None:
    result = number(value)
    if result is None:
        return None
    if not result.is_integer() or not minimum <= result <= maximum:
        raise ValueError("integer is outside the supported range")
    return int(result)


def timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("expected an ISO 8601 timestamp")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return result.astimezone(UTC)


def epoch_timestamp(value: object) -> datetime | None:
    seconds = number(value)
    return datetime.fromtimestamp(seconds, UTC) if seconds is not None else None
