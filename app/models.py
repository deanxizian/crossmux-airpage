from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(slots=True)
class ForecastDay:
    date: date
    high: float | None = None
    low: float | None = None
    precipitation_probability: int | None = None
    weather_code: int | None = None
    description: str = "暂无"


@dataclass(slots=True)
class WeatherSnapshot:
    location: str
    forecasts: list[ForecastDay] = field(default_factory=list)
    available: bool = False


@dataclass(slots=True)
class StockSnapshot:
    symbol: str
    label: str
    price: float | None = None
    change_percent: float | None = None
    points: list[float] = field(default_factory=list)
    available: bool = False


@dataclass(slots=True)
class NewsItem:
    title: str


@dataclass(slots=True)
class NewsSnapshot:
    label: str
    items: list[NewsItem] = field(default_factory=list)
    available: bool = False


@dataclass(slots=True)
class PageData:
    now: datetime
    weather: WeatherSnapshot
    stocks: list[StockSnapshot]
    news: NewsSnapshot
