from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.bmp import quantize_gray4
from app.config import Settings
from app.models import NewsSnapshot, PageData, StockSnapshot, WeatherSnapshot

BLACK = 0
DARK = 85
LIGHT = 170
WHITE = 255
BASE_SIZE = (528, 792)
WEEKDAY_LONG = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
HEADER_DIVIDER_Y = 88
WEATHER_DIVIDER_Y = 323
MARKET_DIVIDER_Y = 558


def _first_existing(candidates: list[str | None]) -> str | None:
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


@dataclass(slots=True)
class FontBook:
    sans_path: str
    mono_path: str

    @classmethod
    def load(cls, settings: Settings) -> FontBook:
        sans = _first_existing(
            [
                settings.font_sans_path,
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
                "/System/Library/Fonts/STHeiti Medium.ttc",
                "/System/Library/Fonts/Hiragino Sans GB.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            ]
        )
        mono = _first_existing(
            [
                settings.font_mono_path,
                "/System/Library/Fonts/SFNSMono.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                sans,
            ]
        )
        if not sans or not mono:
            raise RuntimeError("未找到可用字体；Docker 请安装 fonts-noto-cjk")
        return cls(sans_path=sans, mono_path=mono)

    def sans(self, size: int) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(self.sans_path, size=size)

    def mono(self, size: int) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(self.mono_path, size=size)


def _text_width(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont
) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _draw_centered(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: int = BLACK,
) -> None:
    draw.text((x, y), text, font=font, fill=fill, anchor="ma")


def _draw_right(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: int = BLACK,
) -> None:
    draw.text((x, y), text, font=font, fill=fill, anchor="rm")


def _draw_mini_weather_icon(
    draw: ImageDraw.ImageDraw, center_x: float, top: int, code: int | None
) -> None:
    cx = round(center_x)
    rainy = code is not None and (51 <= code <= 67 or 80 <= code <= 82)
    thunder = code is not None and code >= 95
    snowy = code is not None and (71 <= code <= 77 or 85 <= code <= 86)
    cloudy = code is None or code in {2, 3, 45, 48} or rainy or snowy or thunder

    if code in {0, 1, 2}:
        sun_x = cx - 10 if cloudy else cx
        sun_y = top + 18
        draw.ellipse(
            (sun_x - 10, sun_y - 10, sun_x + 10, sun_y + 10),
            outline=BLACK,
            width=2,
        )
        for angle in range(0, 360, 45):
            radians = math.radians(angle)
            draw.line(
                (
                    sun_x + math.cos(radians) * 14,
                    sun_y + math.sin(radians) * 14,
                    sun_x + math.cos(radians) * 18,
                    sun_y + math.sin(radians) * 18,
                ),
                fill=BLACK,
                width=2,
            )

    if cloudy:
        cloud_outline = (
            (cx - 20, top + 42),
            (cx - 23, top + 40),
            (cx - 25, top + 36),
            (cx - 25, top + 32),
            (cx - 23, top + 28),
            (cx - 20, top + 25),
            (cx - 16, top + 23),
            (cx - 13, top + 23),
            (cx - 10, top + 25),
            (cx - 9, top + 20),
            (cx - 6, top + 16),
            (cx - 3, top + 13),
            (cx + 1, top + 12),
            (cx + 5, top + 13),
            (cx + 9, top + 16),
            (cx + 11, top + 20),
            (cx + 13, top + 25),
            (cx + 17, top + 24),
            (cx + 21, top + 26),
            (cx + 23, top + 29),
            (cx + 25, top + 33),
            (cx + 25, top + 37),
            (cx + 23, top + 40),
            (cx + 20, top + 42),
            (cx - 20, top + 42),
        )
        draw.polygon(cloud_outline, fill=WHITE)
        draw.line(cloud_outline, fill=BLACK, width=2, joint="curve")
    elif code not in {0, 1, 2}:
        draw.ellipse((cx - 15, top + 4, cx + 15, top + 34), outline=BLACK, width=2)

    if thunder:
        draw.polygon(
            (
                (cx + 2, top + 46),
                (cx - 6, top + 58),
                (cx, top + 57),
                (cx - 3, top + 68),
                (cx + 10, top + 52),
                (cx + 4, top + 53),
            ),
            fill=BLACK,
        )
    elif rainy:
        for offset in (-13, 1, 15):
            draw.line(
                (cx + offset, top + 48, cx + offset - 3, top + 56),
                fill=DARK,
                width=2,
            )
    elif snowy:
        for offset in (-13, 1, 15):
            draw.line(
                (cx + offset - 3, top + 53, cx + offset + 3, top + 53),
                fill=DARK,
                width=1,
            )
            draw.line(
                (cx + offset, top + 50, cx + offset, top + 56),
                fill=DARK,
                width=1,
            )


def _forecast_temperature(high: float | None, low: float | None) -> str:
    high_text = str(round(high)) if high is not None else "--"
    low_text = str(round(low)) if low is not None else "--"
    return f"{high_text}°/{low_text}°"


def _forecast_day_label(forecast_date: date, today: date) -> str:
    if forecast_date == today:
        return "今天"
    return WEEKDAY_LONG[forecast_date.weekday()]


def _draw_forecast(
    draw: ImageDraw.ImageDraw,
    fonts: FontBook,
    weather: WeatherSnapshot,
    forecast_days: int,
    today: date,
) -> None:
    _section_title(
        draw,
        fonts,
        f"{weather.location} · {forecast_days}日",
        102,
        "暂无"
        if not weather.available
        else "缓存"
        if weather.info.state == "stale"
        else "",
    )
    forecasts = weather.forecasts[:forecast_days]
    if not forecasts:
        _draw_centered(draw, 264, 211, "未来预报暂不可用", fonts.sans(18), DARK)
        draw.line(
            (12, WEATHER_DIVIDER_Y, 516, WEATHER_DIVIDER_Y),
            fill=BLACK,
            width=2,
        )
        return

    left, right = 16, 512
    column_width = (right - left) / forecast_days
    for index in range(1, forecast_days):
        x = round(left + index * column_width)
        draw.line((x, 143, x, 312), fill=LIGHT, width=1)

    for index, day in enumerate(forecasts):
        center = left + column_width * (index + 0.5)
        _draw_centered(
            draw, center, 142, _forecast_day_label(day.date, today), fonts.sans(15)
        )
        _draw_centered(
            draw,
            center,
            164,
            f"{day.date.month}月{day.date.day}日",
            fonts.sans(11),
            DARK,
        )
        _draw_mini_weather_icon(draw, center, 177, day.weather_code)
        _draw_centered(draw, center, 246, day.description, fonts.sans(14))
        _draw_centered(
            draw,
            center,
            273,
            _forecast_temperature(day.high, day.low),
            fonts.mono(14),
        )
        precipitation = (
            str(day.precipitation_probability)
            if day.precipitation_probability is not None
            else "--"
        )
        _draw_centered(
            draw, center, 300, f"降水 {precipitation}%", fonts.sans(12), DARK
        )

    draw.line((12, WEATHER_DIVIDER_Y, 516, WEATHER_DIVIDER_Y), fill=BLACK, width=2)


def _draw_sparkline(
    draw: ImageDraw.ImageDraw, points: list[float], box: tuple[int, int, int, int]
) -> None:
    x0, y0, x1, y1 = box
    draw.line((x0, (y0 + y1) // 2, x1, (y0 + y1) // 2), fill=LIGHT, width=1)
    if len(points) < 2:
        draw.line(
            (x0 + 10, (y0 + y1) // 2, x1 - 10, (y0 + y1) // 2), fill=DARK, width=2
        )
        return
    low, high = min(points), max(points)
    spread = high - low or 1.0
    coordinates = []
    for index, value in enumerate(points):
        x = x0 + (x1 - x0) * index / (len(points) - 1)
        y = y1 - 3 - (y1 - y0 - 6) * (value - low) / spread
        coordinates.append((round(x), round(y)))
    draw.line(coordinates, fill=DARK, width=2, joint="curve")


def _format_price(stock: StockSnapshot) -> str:
    if stock.price is None:
        return "--"
    if abs(stock.price) >= 10000:
        return f"{stock.price:,.0f}"
    return f"{stock.price:.2f}"


def _draw_market(
    draw: ImageDraw.ImageDraw, fonts: FontBook, stocks: list[StockSnapshot]
) -> None:
    stale = sum(stock.info.state == "stale" for stock in stocks)
    unavailable = sum(not stock.available for stock in stocks)
    notice = " · ".join(
        text
        for text in (
            f"{stale}项缓存" if stale else "",
            f"{unavailable}项暂无" if unavailable else "",
        )
        if text
    )
    _section_title(draw, fonts, "A股 · 自选", 572, notice)
    rows = (633, 695, 757)
    normalized = stocks[:3]
    while len(normalized) < 3:
        normalized.append(StockSnapshot(symbol="--", label="--"))

    for index, (stock, y) in enumerate(zip(normalized, rows, strict=True)):
        label = stock.label or stock.symbol
        label_font = fonts.sans(17 if len(label) <= 5 else 15)
        draw.text((20, y - 8), label, font=label_font, fill=BLACK, anchor="lm")
        if stock.symbol and stock.symbol != label:
            draw.text(
                (20, y + 13), stock.symbol, font=fonts.mono(10), fill=DARK, anchor="lm"
            )
        _draw_right(draw, 298, y, _format_price(stock), fonts.mono(18))

        if stock.change_percent is None:
            change_text = "--"
        else:
            sign = "+" if stock.change_percent >= 0 else "−"
            change_text = f"{sign}{abs(stock.change_percent):.2f}%"
        _draw_right(draw, 407, y, change_text, fonts.mono(14))
        if stock.change_percent is not None:
            if stock.change_percent >= 0:
                draw.polygon(((409, y + 7), (416, y - 6), (423, y + 7)), fill=BLACK)
            else:
                draw.polygon(((409, y - 6), (423, y - 6), (416, y + 7)), outline=BLACK)
        _draw_sparkline(draw, stock.points, (434, y - 17, 509, y + 17))
        if index < 2:
            draw.line((20, y + 27, 508, y + 27), fill=LIGHT, width=1)


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> str:
    if _text_width(draw, text, font) <= max_width:
        return text
    ellipsis = "…"
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if _text_width(draw, text[:middle] + ellipsis, font) <= max_width:
            low = middle
        else:
            high = middle - 1
    return text[:low].rstrip() + ellipsis


def _draw_news(draw: ImageDraw.ImageDraw, fonts: FontBook, news: NewsSnapshot) -> None:
    _section_title(
        draw,
        fonts,
        news.label,
        337,
        "暂无" if not news.available else "缓存" if news.info.state == "stale" else "",
    )
    if not news.items:
        draw.text(
            (20, 440), "新闻暂不可用", font=fonts.sans(17), fill=DARK, anchor="lm"
        )
        return

    headline_font = fonts.sans(15)
    rows = (393, 438, 483, 528)
    visible_items = news.items[:4]
    for index, (item, y) in enumerate(zip(visible_items, rows, strict=False)):
        draw.ellipse((20, y - 2, 24, y + 2), fill=BLACK)
        headline = _fit_text(draw, item.title, headline_font, 476)
        draw.text((32, y), headline, font=headline_font, fill=BLACK, anchor="lm")
        if index < len(visible_items) - 1:
            draw.line((32, y + 22, 508, y + 22), fill=LIGHT, width=1)


def _section_title(
    draw: ImageDraw.ImageDraw, fonts: FontBook, title: str, y: int, notice: str
) -> None:
    notice_width = _text_width(draw, notice, fonts.sans(12)) + 16 if notice else 0
    draw.text(
        (20, y),
        _fit_text(draw, title, fonts.sans(21), 488 - notice_width),
        font=fonts.sans(21),
        fill=BLACK,
    )
    if notice:
        draw.text((508, y + 13), notice, font=fonts.sans(12), fill=DARK, anchor="rm")


def render_page(data: PageData, settings: Settings) -> Image.Image:
    fonts = FontBook.load(settings)
    image = Image.new("L", BASE_SIZE, WHITE)
    draw = ImageDraw.Draw(image)

    draw.text((18, 5), data.now.strftime("%H:%M"), font=fonts.mono(59), fill=BLACK)
    date_text = (
        f"{data.now.month}月{data.now.day}日 · {WEEKDAY_LONG[data.now.weekday()]}"
    )
    draw.text((508, 49), date_text, font=fonts.sans(20), fill=BLACK, anchor="rm")
    draw.line((12, HEADER_DIVIDER_Y, 516, HEADER_DIVIDER_Y), fill=BLACK, width=2)
    _draw_forecast(
        draw,
        fonts,
        data.weather,
        settings.weather_forecast_days,
        data.now.date(),
    )
    _draw_news(draw, fonts, data.news)
    draw.line((12, MARKET_DIVIDER_Y, 516, MARKET_DIVIDER_Y), fill=BLACK, width=2)
    _draw_market(draw, fonts, data.stocks)

    image = quantize_gray4(image)
    if image.size != (settings.width, settings.height):
        image = image.resize(
            (settings.width, settings.height), Image.Resampling.NEAREST
        )
    return image
