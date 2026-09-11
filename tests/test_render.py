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
def test_weather_icons_fit_their_slot(code) -> None:
    image = Image.new("L", (160, 160), WHITE)
    center_x, top = 80, 40
    _draw_mini_weather_icon(ImageDraw.Draw(image), center_x, top, code)
    bounds = ImageOps.invert(image).getbbox()
    assert bounds is not None
    left, upper, right, lower = bounds

    # A partly cloudy sun can extend to the left; the cloud body remains
    # centered and is checked against the other cloud variants below.
    if code != 2:
        assert abs((left + right - 1) / 2 - center_x) <= 0.5
    assert center_x - WEATHER_ICON_SIZE // 2 <= left
    assert right <= center_x + WEATHER_ICON_SIZE // 2
    assert right - left <= WEATHER_ICON_SIZE
    assert top <= upper < lower <= top + WEATHER_ICON_SIZE
    assert set(image.tobytes()).issubset({0, 85, 170, 255})


@pytest.mark.parametrize(
    "code", [code for code in WEATHER_DESCRIPTIONS if code not in {0, 1}] + [None]
)
def test_cloud_bodies_share_an_outline_and_baseline(code) -> None:
    reference = Image.new("L", (100, 80), WHITE)
    image = Image.new("L", reference.size, WHITE)
    _draw_mini_weather_icon(ImageDraw.Draw(reference), 50, 0, 3)
    _draw_mini_weather_icon(ImageDraw.Draw(image), 50, 0, code)
    bounds = ImageOps.invert(reference).getbbox()
    assert bounds is not None

    baseline = max(
        y
        for y in range(image.height)
        if all(image.getpixel((x, y)) == BLACK for x in range(30, 71))
    )
    assert baseline == bounds[3] - 1
    # The partly cloudy sun can add pixels above/left of the cloud, but cannot
    # move its outline. Precipitation must not move the cloud either.
    assert all(
        actual == BLACK
        for expected, actual in zip(reference.tobytes(), image.tobytes(), strict=True)
        if expected == BLACK
    )


@pytest.mark.parametrize("code", [0, 1, -1, 50])
def test_sun_and_fallback_are_centered_on_the_cloud_body(code) -> None:
    centers = []
    for weather_code in (3, code):
        image = Image.new("L", (100, 80), WHITE)
        _draw_mini_weather_icon(ImageDraw.Draw(image), 50, 0, weather_code)
        bounds = ImageOps.invert(image).getbbox()
        assert bounds is not None
        centers.append((bounds[1] + bounds[3] - 1) / 2)
    assert abs(centers[0] - centers[1]) <= 0.5


def test_partly_cloudy_sun_is_visible_without_excessive_overhang() -> None:
    image = Image.new("L", (100, 80), WHITE)
    draw = ImageDraw.Draw(image)
    with patch.object(draw, "ellipse", wraps=draw.ellipse) as ellipse:
        _draw_mini_weather_icon(draw, 50, 0, 2)
    assert ellipse.call_count == 1

    sun = Image.new("L", image.size, WHITE)
    ImageDraw.Draw(sun).ellipse(*ellipse.call_args.args, **ellipse.call_args.kwargs)
    cloud = Image.new("L", image.size, WHITE)
    _draw_mini_weather_icon(ImageDraw.Draw(cloud), 50, 0, 3)
    sun_pixels = sum(value == BLACK for value in sun.tobytes())
    visible_pixels = sum(
        expected == BLACK and actual == BLACK and cloud_pixel == WHITE
        for expected, actual, cloud_pixel in zip(
            sun.tobytes(), image.tobytes(), cloud.tobytes(), strict=True
        )
    )
    assert visible_pixels / sun_pixels >= 0.5
    cloud_bounds = ImageOps.invert(cloud).getbbox()
    icon_bounds = ImageOps.invert(image).getbbox()
    assert cloud_bounds is not None and icon_bounds is not None
    assert 0 <= cloud_bounds[0] - icon_bounds[0] <= 3


@pytest.mark.parametrize("forecast_days", [1, 5])
@pytest.mark.parametrize("code", [*WEATHER_DESCRIPTIONS, None, -1, 50, 100])
def test_weather_icons_leave_space_for_date_and_description(
    settings, code, forecast_days
) -> None:
    fonts = FontBook.load(settings)
    today = date(2026, 12, 31)
    description = weather_description(code)
    weather = WeatherSnapshot(
        location="上海",
        forecasts=[ForecastDay(today, 30, 24, 100, code, description)],
        available=True,
    )
    image = Image.new("L", (528, 792), WHITE)
    draw = ImageDraw.Draw(image)
    with (
        patch.object(draw, "text", wraps=draw.text) as text,
        patch(
            "app.render._draw_mini_weather_icon", wraps=_draw_mini_weather_icon
        ) as icon,
    ):
        _draw_forecast(draw, fonts, weather, forecast_days, today)

    # Measure the positions and fonts actually used by the forecast, so a later
    # layout change cannot silently invalidate this clearance check.
    icon_image = Image.new("L", image.size, WHITE)
    _, center_x, top, weather_code = icon.call_args.args
    assert top == WEATHER_ICON_TOP
    _draw_mini_weather_icon(ImageDraw.Draw(icon_image), center_x, top, weather_code)
    bounds = ImageOps.invert(icon_image).getbbox()
    assert bounds is not None
    text_bounds = {
        call.args[1]: draw.textbbox(
            call.args[0],
            call.args[1],
            font=call.kwargs["font"],
            anchor=call.kwargs.get("anchor"),
        )
        for call in text.call_args_list
    }
    assert bounds[1] - text_bounds["12月31日"][3] >= 12
    assert text_bounds[description][1] - bounds[3] >= 12
    assert text_bounds["30°/24°"][1] - text_bounds[description][3] >= 8
    assert text_bounds["降水概率 100%"][1] - text_bounds["30°/24°"][3] >= 8


@pytest.mark.parametrize("code", [95, 96, 99])
def test_lightning_is_hollow_and_partly_hidden_behind_cloud(code) -> None:
    image = Image.new("L", (100, 80), WHITE)
    draw = ImageDraw.Draw(image)
    with patch.object(draw, "polygon", wraps=draw.polygon) as polygons:
        _draw_mini_weather_icon(draw, 50, 0, code)
    bolt_call = next(
        call for call in polygons.call_args_list if call.kwargs.get("outline") == BLACK
    )
    raw_bolt = Image.new("L", image.size, WHITE)
    ImageDraw.Draw(raw_bolt).polygon(*bolt_call.args, **bolt_call.kwargs)
    raw_bounds = ImageOps.invert(raw_bolt).getbbox()
    assert raw_bounds is not None

    cloud = Image.new("L", image.size, WHITE)
    _draw_mini_weather_icon(ImageDraw.Draw(cloud), 50, 0, 3)
    cloud_bounds = ImageOps.invert(cloud).getbbox()
    assert cloud_bounds is not None
    cloud_baseline = cloud_bounds[3] - 1
    assert 2 <= cloud_baseline - raw_bounds[1] + 1 <= 4
    height = raw_bounds[3] - raw_bounds[1]
    width = raw_bounds[2] - raw_bounds[0]
    assert 20 <= height <= 22
    assert 11 <= width <= 14
    assert height / width >= 1.5
    # The cloud must actually paint over the top of the bolt, not just touch it.
    above_baseline = (0, 0, image.width, cloud_baseline + 1)
    assert image.crop(above_baseline).tobytes() == cloud.crop(above_baseline).tobytes()

    below_cloud = image.crop((0, cloud_baseline + 1, image.width, image.height))
    bolt_bounds = ImageOps.invert(below_cloud).getbbox()
    assert bolt_bounds is not None
    assert bolt_bounds[1] == 0
    assert 14 <= bolt_bounds[3] - bolt_bounds[1] <= 17

    visible_bolt = image.crop(
        (raw_bounds[0], cloud_baseline, raw_bounds[2], raw_bounds[3])
    )
    bolt = ImageOps.expand(visible_bolt, border=1, fill=WHITE)
    # Paint the outside background gray; a closed, hollow bolt keeps a white core.
    ImageDraw.floodfill(bolt, (0, 0), 170)
    assert sum(value == WHITE for value in bolt.tobytes()) >= 12


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
