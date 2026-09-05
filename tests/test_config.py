from __future__ import annotations

import pytest

from app.config import Settings


def test_defaults_match_the_shanghai_page() -> None:
    settings = Settings.from_env({})
    assert settings.weather_location == "上海"
    assert settings.weather_latitude == 31.2304
    assert settings.weather_longitude == 121.4737
    assert settings.stock_symbols == ("000001.SS", "601727.SS", "600021.SS")
    assert settings.stock_labels == ("上证指数", "上海电气", "上海电力")


def test_market_is_index_plus_two_environment_stocks() -> None:
    settings = Settings.from_env(
        {
            "MARKET_INDEX_SYMBOL": "000300.SS",
            "MARKET_INDEX_LABEL": "沪深300",
            "STOCK_SYMBOLS": "601318.SS,000858.SZ,600036.SS",
            "STOCK_LABELS": "中国平安,五粮液,招商银行",
        }
    )
    assert settings.stock_symbols == ("000300.SS", "601318.SS", "000858.SZ")
    assert settings.stock_labels == ("沪深300", "中国平安", "五粮液")


def test_weather_forecast_days_is_limited_to_screen_capacity() -> None:
    settings = Settings.from_env({"WEATHER_FORECAST_DAYS": "12"})
    assert settings.weather_forecast_days == 5


def test_news_items_is_limited_to_screen_capacity() -> None:
    settings = Settings.from_env({"NEWS_ITEMS": "12"})
    assert settings.news_items == 4


def test_push_interval_has_one_minute_floor() -> None:
    settings = Settings.from_env({"AIRPAGE_PUSH_INTERVAL_MINUTES": "0"})
    assert settings.airpage_push_interval_minutes == 1


def test_custom_symbols_do_not_inherit_unrelated_names() -> None:
    settings = Settings.from_env(
        {"MARKET_INDEX_SYMBOL": "000300.SS", "STOCK_SYMBOLS": "600519.SS,000001.SZ"}
    )
    assert settings.stock_labels == settings.stock_symbols


@pytest.mark.parametrize(
    "labels,expected",
    [
        ("茅台", ("茅台", "000001.SZ")),
        (",平安银行", ("600519.SS", "平安银行")),
        ("", ("600519.SS", "000001.SZ")),
    ],
)
def test_partial_labels_keep_their_symbol_positions(labels, expected) -> None:
    settings = Settings.from_env(
        {"STOCK_SYMBOLS": "600519.SS,000001.SZ", "STOCK_LABELS": labels}
    )
    assert settings.stock_labels[1:] == expected


def test_reordered_known_symbols_keep_their_names() -> None:
    settings = Settings.from_env({"STOCK_SYMBOLS": "600021.SS,601727.SS"})
    assert settings.stock_labels[1:] == ("上海电力", "上海电气")
