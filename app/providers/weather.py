from __future__ import annotations

from datetime import date

import httpx

from app.config import Settings
from app.models import ForecastDay, WeatherSnapshot

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
    if not isinstance(values, list) or index >= len(values):
        return None
    return values[index]


def fetch_weather(settings: Settings, client: httpx.Client) -> WeatherSnapshot:
    response = client.get(
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
    for index, raw_date in enumerate(dates[: settings.weather_forecast_days]):
        try:
            forecast_date = date.fromisoformat(str(raw_date))
        except ValueError:
            continue
        forecast_code = _daily_value(daily, "weather_code", index)
        forecast.append(
            ForecastDay(
                date=forecast_date,
                high=_daily_value(daily, "temperature_2m_max", index),
                low=_daily_value(daily, "temperature_2m_min", index),
                precipitation_probability=_daily_value(
                    daily, "precipitation_probability_max", index
                ),
                weather_code=forecast_code,
                description=WEATHER_DESCRIPTIONS.get(forecast_code, "未知"),
            )
        )
    return WeatherSnapshot(
        location=settings.weather_location,
        forecasts=forecast,
        available=True,
    )


def unavailable_weather(settings: Settings) -> WeatherSnapshot:
    return WeatherSnapshot(location=settings.weather_location)
