from __future__ import annotations

import asyncio

import pytest

from app.providers.weather import fetch_weather
from app.weather_codes import WEATHER_DESCRIPTIONS, weather_description


class StubResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "daily": {
                "time": [
                    "2026-09-04",
                    "2026-09-05",
                    "2026-09-06",
                    "2026-09-07",
                    "2026-09-08",
                    "2026-09-09",
                ],
                "weather_code": [2, 2, 61, 0, 2, 95],
                "temperature_2m_max": [31, 32, 29, 31, 30, 27],
                "temperature_2m_min": [20, 23, 21, 20, 21, 20],
                "precipitation_probability_max": [10, 20, 60, 10, 20, 70],
            },
        }


class StubClient:
    def __init__(self) -> None:
        self.params: dict[str, object] = {}

    async def get(self, _url: str, params: dict[str, object]) -> StubResponse:
        self.params = params
        return StubResponse()


def test_fetch_weather_keeps_today_and_next_four_days(settings) -> None:
    client = StubClient()
    weather = asyncio.run(fetch_weather(settings, client))  # type: ignore[arg-type]

    assert client.params["forecast_days"] == 5
    assert len(weather.forecasts) == 5
    assert weather.forecasts[0].date.isoformat() == "2026-09-04"
    assert weather.forecasts[0].description == "局部多云"
    assert weather.forecasts[2].description == "小雨"
    assert weather.forecasts[-1].precipitation_probability == 20


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (0, "晴朗无云"),
        (1, "大部晴朗无云"),
        (2, "局部多云"),
        (3, "多云"),
        (45, "雾"),
        (48, "雾伴雾凇"),
        (51, "微雨"),
        (53, "微雨"),
        (55, "微雨"),
        (56, "冻细雨"),
        (57, "冻细雨"),
        (61, "小雨"),
        (63, "中雨"),
        (65, "大雨"),
        (66, "冻雨"),
        (67, "冻雨"),
        (71, "小雪"),
        (73, "中雪"),
        (75, "大雪"),
        (77, "米雪"),
        (80, "阵雨"),
        (81, "阵雨"),
        (82, "强阵雨"),
        (85, "阵雪"),
        (86, "强阵雪"),
        (95, "雷暴雨"),
        (96, "雷暴伴雹"),
        (99, "雷暴伴雹"),
    ],
)
def test_weather_terms_preserve_wmo_meanings(code, expected) -> None:
    assert weather_description(code) == expected


@pytest.mark.parametrize("code", [None, -1, 4, 100])
def test_unknown_weather_codes_are_not_guessed(code) -> None:
    assert code not in WEATHER_DESCRIPTIONS
    assert weather_description(code) == "未知"
