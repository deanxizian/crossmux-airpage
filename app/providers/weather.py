from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import httpx

from app.config import Settings
from app.models import ForecastDay, SnapshotInfo, WeatherSnapshot
from app.validation import integer, number

WEATHER_DESCRIPTIONS = {
    0: "晴",
    1: "晴间多云",
    2: "多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "毛毛雨",
    53: "毛毛雨",
    55: "毛毛雨",
    56: "冻雨",
    57: "冻雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "冻雨",
    67: "冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "米雪",
    80: "阵雨",
    81: "阵雨",
    82: "强阵雨",
    85: "阵雪",
    86: "强阵雪",
    95: "雷雨",
    96: "雷雨冰雹",
    99: "强雷雨",
}


def _daily_value(daily: dict[str, object], key: str, index: int) -> object | None:
    values = daily.get(key)
    if values is None:
        return None
    if not isinstance(values, list):
        raise TypeError("Open-Meteo 每日字段必须是数组")
    if index >= len(values):
        return None
    return values[index]


async def fetch_weather(
    settings: Settings, client: httpx.AsyncClient
) -> WeatherSnapshot:
    response = await client.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": settings.weather_latitude,
            "longitude": settings.weather_longitude,
            "daily": (
                "weather_code,temperature_2m_max,temperature_2m_min,"
                "precipitation_probability_max"
            ),
            "timezone": settings.weather_timezone,
            "forecast_days": settings.weather_forecast_days,
        },
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise TypeError("Open-Meteo 返回格式无效")
    daily = payload.get("daily")
    if not isinstance(daily, dict):
        raise TypeError("Open-Meteo 响应缺少 daily")
    forecast: list[ForecastDay] = []
    dates = daily.get("time") or []
    if not isinstance(dates, list):
        raise TypeError("Open-Meteo 日期必须是数组")
    seen: set[date] = set()
    for index, raw_date in enumerate(dates[: settings.weather_forecast_days]):
        try:
            forecast_date = date.fromisoformat(str(raw_date))
        except ValueError:
            continue
        if forecast_date in seen:
            continue
        seen.add(forecast_date)
        forecast_code = integer(_daily_value(daily, "weather_code", index), 0, 99)
        high = number(_daily_value(daily, "temperature_2m_max", index))
        low = number(_daily_value(daily, "temperature_2m_min", index))
        precipitation = integer(
            _daily_value(daily, "precipitation_probability_max", index), 0, 100
        )
        if all(value is None for value in (forecast_code, high, low, precipitation)):
            continue
        if high is not None and low is not None and high < low:
            raise ValueError("最高温低于最低温")
        forecast.append(
            ForecastDay(
                date=forecast_date,
                high=high,
                low=low,
                precipitation_probability=precipitation,
                weather_code=forecast_code,
                description=WEATHER_DESCRIPTIONS.get(forecast_code, "未知"),
            )
        )
    if not forecast:
        raise ValueError("Open-Meteo 没有可用预报")
    return WeatherSnapshot(
        location=settings.weather_location,
        forecasts=forecast,
        available=True,
        info=SnapshotInfo(
            data_at=datetime.combine(
                min(day.date for day in forecast),
                time.min,
                ZoneInfo(settings.weather_timezone),
            ),
            state="fresh",
        ),
    )


def unavailable_weather(settings: Settings) -> WeatherSnapshot:
    return WeatherSnapshot(location=settings.weather_location)
