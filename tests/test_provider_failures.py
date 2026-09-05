from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.providers.news import fetch_news
from app.providers.stocks import fetch_stock
from app.providers.weather import fetch_weather


def fetch(function, settings, payload, *args):
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, content=json.dumps(payload).encode()
                )
            )
        ) as client:
            return await function(settings, client, *args)

    return asyncio.run(run())


@pytest.mark.parametrize(
    "daily", [{}, {"time": []}, {"time": "2026-09-05"}, {"time": ["invalid"]}]
)
def test_weather_rejects_empty_or_invalid_days(settings, daily) -> None:
    with pytest.raises((ValueError, TypeError)):
        fetch(fetch_weather, settings, {"daily": daily})


@pytest.mark.parametrize("bad", ["hot", "31", True, {}, float("nan"), float("inf")])
def test_weather_rejects_invalid_numbers_before_rendering(settings, bad) -> None:
    with pytest.raises((ValueError, TypeError)):
        fetch(
            fetch_weather,
            settings,
            {
                "daily": {
                    "time": ["2026-09-05"],
                    "weather_code": [2],
                    "temperature_2m_max": [bad],
                }
            },
        )


@pytest.mark.parametrize("probability", [-1, 101, 2.5, "20%"])
def test_weather_validates_probability(settings, probability) -> None:
    with pytest.raises((ValueError, TypeError)):
        fetch(
            fetch_weather,
            settings,
            {
                "daily": {
                    "time": ["2026-09-05"],
                    "precipitation_probability_max": [probability],
                }
            },
        )


@pytest.mark.parametrize("bad", ["bad", True, {}, float("nan"), float("inf")])
def test_stock_rejects_invalid_prices_and_points(settings, bad) -> None:
    payload = {
        "chart": {
            "result": [
                {
                    "meta": {"regularMarketPrice": 6},
                    "indicators": {"quote": [{"close": [6, bad]}]},
                }
            ]
        }
    }
    with pytest.raises((ValueError, TypeError)):
        fetch(fetch_stock, settings, payload, "601727.SS", "上海电气")


def test_stock_preserves_quote_time_and_zero_price(settings) -> None:
    result = fetch(
        fetch_stock,
        settings,
        {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "regularMarketPrice": 0,
                            "previousClose": 1,
                            "regularMarketTime": 1750000000,
                        },
                        "indicators": {"quote": [{"close": [None, 0]}]},
                    }
                ]
            }
        },
        "TEST",
        "TEST",
    )
    assert result.available and result.price == 0
    assert result.change_percent == -100
    assert result.info.data_at.timestamp() == 1750000000


def test_news_preserves_upstream_stale_and_published_time(tmp_path) -> None:
    from app.config import Settings

    settings = Settings.from_env(
        {
            "NEWS_API_BASE_URL": "https://news.example.invalid",
            "OUTPUT_DIR": str(tmp_path),
        }
    )
    result = fetch(
        fetch_news,
        settings,
        {
            "stale": True,
            "items": [{"content": "测试标题", "published_at": "2026-09-04T01:00:00Z"}],
        },
    )
    assert result.info.state == "stale"
    assert result.info.data_at == result.items[0].published_at
    assert result.info.data_at.tzinfo is not None


def test_weather_rejects_wrong_array_type(settings) -> None:
    with pytest.raises(TypeError):
        fetch(
            fetch_weather,
            settings,
            {
                "daily": {
                    "time": ["2026-09-05"],
                    "weather_code": [2],
                    "temperature_2m_max": "31",
                }
            },
        )
