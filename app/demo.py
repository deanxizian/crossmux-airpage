"""Deterministic offline examples, never real weather, news, or quotations."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import Settings
from app.models import (
    ForecastDay,
    NewsItem,
    NewsSnapshot,
    PageData,
    SnapshotInfo,
    StockSnapshot,
    WeatherSnapshot,
)


def demo_page(settings: Settings, now: datetime) -> PageData:
    now = now.astimezone(ZoneInfo(settings.timezone))
    codes = (2, 61, 3, 0, 2)
    descriptions = ("多云", "小雨", "阴", "晴", "多云")
    weather = WeatherSnapshot(
        location=f"{settings.weather_location}（示例）",
        forecasts=[
            ForecastDay(
                now.date() + timedelta(days=i),
                30 - i,
                24 - i,
                (20, 70, 30, 0, 10)[i],
                codes[i],
                descriptions[i],
            )
            for i in range(settings.weather_forecast_days)
        ],
        available=True,
        info=SnapshotInfo(now, now, "fresh"),
    )
    stocks = [
        StockSnapshot(
            symbol,
            label,
            price,
            change,
            [price * factor for factor in (0.99, 1.0, 0.995, 1.003, 1.001, 1.0)],
            True,
            SnapshotInfo(now, now, "fresh"),
        )
        for symbol, label, price, change in zip(
            settings.stock_symbols,
            settings.stock_labels,
            (3200.00, 6.50, 13.00),
            (0.25, -0.30, 0.46),
            strict=False,
        )
    ]
    news = NewsSnapshot(
        "新闻 · 离线示例",
        [
            NewsItem(title, now)
            for title in (
                "城市图书馆延长周末开放时间",
                "社区公园新增步行路线和休息座椅",
                "本地科技展将展示节能与环保新技术",
                "周末阅读活动开放预约，欢迎市民参加",
            )
        ][: settings.news_items],
        True,
        SnapshotInfo(now, now, "fresh"),
    )
    return PageData(now, weather, stocks, news)
