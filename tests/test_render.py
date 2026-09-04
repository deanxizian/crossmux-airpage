from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

from app.models import (
    ForecastDay,
    NewsItem,
    NewsSnapshot,
    PageData,
    StockSnapshot,
    WeatherSnapshot,
)
from app.render import (
    BLACK,
    HEADER_DIVIDER_Y,
    MARKET_DIVIDER_Y,
    WEATHER_DIVIDER_Y,
    WHITE,
    _draw_mini_weather_icon,
    _forecast_day_label,
    render_page,
)


def test_cloud_icon_has_a_continuous_closed_baseline() -> None:
    image = Image.new("L", (100, 80), WHITE)
    draw = ImageDraw.Draw(image)
    _draw_mini_weather_icon(draw, 50, 0, 3)

    assert all(image.getpixel((x, 42)) == BLACK for x in range(30, 71))
    ink_x = [
        x
        for x in range(image.width)
        for y in range(image.height)
        if image.getpixel((x, y)) != WHITE
    ]
    assert max(ink_x) - min(ink_x) + 1 <= 53


def test_today_forecast_uses_an_explicit_label() -> None:
    today = date(2026, 9, 4)
    assert _forecast_day_label(today, today) == "今天"
    assert _forecast_day_label(date(2026, 9, 5), today) == "周六"


def test_render_is_native_size_and_four_gray(settings) -> None:
    now = datetime(2026, 9, 4, 9, 41, tzinfo=ZoneInfo("Asia/Shanghai"))
    data = PageData(
        now=now,
        weather=WeatherSnapshot(
            location="上海",
            forecasts=[
                ForecastDay(date(2026, 9, 4), 31, 20, 10, 2, "多云"),
                ForecastDay(date(2026, 9, 5), 32, 23, 20, 2, "多云"),
                ForecastDay(date(2026, 9, 6), 29, 21, 60, 61, "小雨"),
                ForecastDay(date(2026, 9, 7), 31, 20, 10, 0, "晴"),
                ForecastDay(date(2026, 9, 8), 30, 21, 20, 2, "多云"),
            ],
            available=True,
        ),
        stocks=[
            StockSnapshot(
                symbol="000001.SS",
                label="上证指数",
                price=3284.57,
                change_percent=0.48,
                points=[3200, 3230, 3215, 3260, 3284],
                available=True,
            ),
            StockSnapshot(
                symbol="601727.SS",
                label="上海电气",
                price=6.62,
                change_percent=1.38,
                points=[6.51, 6.55, 6.58, 6.60, 6.62],
                available=True,
            ),
            StockSnapshot(
                symbol="600021.SS",
                label="上海电力",
                price=13.42,
                change_percent=0.68,
                points=[13.1, 13.2, 13.25, 13.35, 13.42],
                available=True,
            ),
        ],
        news=NewsSnapshot(
            label="新浪 · 快讯",
            items=[
                NewsItem("首条新闻标题"),
                NewsItem("第二条新闻标题"),
                NewsItem("第三条新闻标题"),
                NewsItem("第四条新闻标题"),
            ],
            available=True,
        ),
    )
    image = render_page(data, settings)
    assert image.size == (528, 792)
    assert set(image.tobytes()).issubset({0, 85, 170, 255})
    assert image.crop((260, 8, 516, HEADER_DIVIDER_Y)).getextrema()[0] < WHITE
    section_heights = (
        WEATHER_DIVIDER_Y - HEADER_DIVIDER_Y,
        MARKET_DIVIDER_Y - WEATHER_DIVIDER_Y,
        792 - MARKET_DIVIDER_Y,
    )
    assert max(section_heights) - min(section_heights) <= 2
