from __future__ import annotations

from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from PIL import Image, ImageDraw, ImageOps

from app.demo import demo_page
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
    WEATHER_ICON_SIZE,
    WEATHER_ICON_TOP,
    WHITE,
    FontBook,
    _draw_forecast,
    _draw_mini_weather_icon,
    _forecast_day_label,
    render_page,
)
from app.weather_codes import WEATHER_DESCRIPTIONS, weather_description


def test_cloud_icon_has_a_continuous_closed_baseline() -> None:
    image = Image.new("L", (100, 80), WHITE)
    draw = ImageDraw.Draw(image)
    _draw_mini_weather_icon(draw, 50, 0, 3)

    bounds = ImageOps.invert(image).getbbox()
    assert bounds is not None
    baseline = bounds[3] - 1
    assert all(image.getpixel((x, baseline)) == BLACK for x in range(30, 71))
    ink_x = [
        x
        for x in range(image.width)
        for y in range(image.height)
        if image.getpixel((x, y)) != WHITE
    ]
    assert max(ink_x) - min(ink_x) + 1 <= 53


@pytest.mark.parametrize("code", [*WEATHER_DESCRIPTIONS, None, -1, 50, 100])
def test_weather_icons_share_a_center_and_fit_their_slot(code) -> None:
    image = Image.new("L", (160, 160), WHITE)
    center_x, top = 80, 40
    _draw_mini_weather_icon(ImageDraw.Draw(image), center_x, top, code)
    bounds = ImageOps.invert(image).getbbox()
    assert bounds is not None
    left, upper, right, lower = bounds

    assert abs((left + right - 1) / 2 - center_x) <= 0.5
    expected_center_y = top + (WEATHER_ICON_SIZE - 1) / 2
    assert abs((upper + lower - 1) / 2 - expected_center_y) <= 0.5
    assert right - left <= WEATHER_ICON_SIZE
    assert top <= upper < lower <= top + WEATHER_ICON_SIZE
    assert set(image.tobytes()).issubset({0, 85, 170, 255})


@pytest.mark.parametrize("code", [*WEATHER_DESCRIPTIONS, None])
def test_weather_icons_leave_space_for_date_and_description(settings, code) -> None:
    fonts = FontBook.load(settings)
    image = Image.new("L", (528, 792), WHITE)
    draw = ImageDraw.Draw(image)
    _draw_mini_weather_icon(draw, 64, WEATHER_ICON_TOP, code)
    bounds = ImageOps.invert(image).getbbox()
    assert bounds is not None
    date_bottom = draw.textbbox(
        (64, 164), "12月31日", font=fonts.sans(11), anchor="ma"
    )[3]
    description_top = draw.textbbox(
        (64, 246), weather_description(code), font=fonts.sans(14), anchor="ma"
    )[1]

    assert bounds[1] - date_bottom >= 8
    assert description_top - bounds[3] >= 10


@pytest.mark.parametrize("code", [95, 96, 99])
def test_lightning_is_hollow_compact_and_close_to_cloud(code) -> None:
    image = Image.new("L", (100, 80), WHITE)
    _draw_mini_weather_icon(ImageDraw.Draw(image), 50, 0, code)
    cloud_baseline = max(
        y
        for y in range(image.height)
        if all(image.getpixel((x, y)) == BLACK for x in range(30, 71))
    )
    below_cloud = image.crop((0, cloud_baseline + 1, image.width, image.height))
    bolt_bounds = ImageOps.invert(below_cloud).getbbox()
    assert bolt_bounds is not None
    assert 1 <= bolt_bounds[1] <= 2
    assert bolt_bounds[3] - bolt_bounds[1] <= 18

    bolt = ImageOps.expand(below_cloud.crop(bolt_bounds), border=1, fill=WHITE)
    # Paint the outside background gray; a closed, hollow bolt keeps a white core.
    ImageDraw.floodfill(bolt, (0, 0), 170)
    assert sum(value == WHITE for value in bolt.tobytes()) >= 4


def test_today_forecast_uses_an_explicit_label() -> None:
    today = date(2026, 9, 4)
    assert _forecast_day_label(today, today) == "今天"
    assert _forecast_day_label(date(2026, 9, 5), today) == "周六"


def test_weather_terms_and_probabilities_fit_five_columns(settings) -> None:
    fonts = FontBook.load(settings)
    draw = ImageDraw.Draw(Image.new("L", (528, 792), WHITE))
    max_width = (512 - 16) / 5 - 12
    for text in WEATHER_DESCRIPTIONS.values():
        x0, _, x1, _ = draw.textbbox((0, 0), text, font=fonts.sans(14))
        assert x1 - x0 <= max_width, text
    for probability in (0, 9, 99, 100, "--"):
        text = f"降水概率 {probability}%"
        x0, _, x1, _ = draw.textbbox((0, 0), text, font=fonts.sans(12))
        assert x1 - x0 <= max_width, text


@pytest.mark.parametrize("probability", [0, 99, 100, None])
def test_render_labels_precipitation_as_probability(settings, probability) -> None:
    today = date(2026, 9, 7)
    weather = WeatherSnapshot(
        location="上海",
        forecasts=[ForecastDay(today, 30, 24, probability, 53, "微雨")],
        available=True,
    )
    draw = ImageDraw.Draw(Image.new("L", (528, 792), WHITE))
    with patch.object(draw, "text", wraps=draw.text) as text:
        _draw_forecast(draw, FontBook.load(settings), weather, 5, today)
    expected = f"降水概率 {probability if probability is not None else '--'}%"
    assert expected in [call.args[1] for call in text.call_args_list]


def test_demo_uses_current_weather_terms(settings) -> None:
    now = datetime(2026, 9, 7, 9, 41, tzinfo=ZoneInfo("Asia/Shanghai"))
    weather = demo_page(settings, now).weather
    assert all(
        day.description == weather_description(day.weather_code)
        for day in weather.forecasts
    )
    assert "微雨" in [day.description for day in weather.forecasts]


def test_render_is_native_size_and_four_gray(settings) -> None:
    now = datetime(2026, 9, 4, 9, 41, tzinfo=ZoneInfo("Asia/Shanghai"))
    data = PageData(
        now=now,
        weather=WeatherSnapshot(
            location="上海",
            forecasts=[
                ForecastDay(date(2026, 9, 4), 31, 20, 10, 2, "局部多云"),
                ForecastDay(date(2026, 9, 5), 32, 23, 20, 2, "局部多云"),
                ForecastDay(date(2026, 9, 6), 29, 21, 60, 61, "小雨"),
                ForecastDay(date(2026, 9, 7), 31, 20, 10, 0, "晴朗无云"),
                ForecastDay(date(2026, 9, 8), 30, 21, 20, 2, "局部多云"),
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
