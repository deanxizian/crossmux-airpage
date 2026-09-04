from __future__ import annotations

from urllib.parse import quote

import httpx

from app.config import Settings
from app.models import StockSnapshot

YAHOO_CHART_URL = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"


def fetch_stock(
    settings: Settings, client: httpx.Client, symbol: str, label: str
) -> StockSnapshot:
    response = client.get(
        YAHOO_CHART_URL.format(symbol=quote(symbol, safe="")),
        params={"range": settings.stock_range, "interval": settings.stock_interval},
        headers={"User-Agent": "Mozilla/5.0 (CrossMux AirPage/0.1)"},
    )
    response.raise_for_status()
    result = (((response.json().get("chart") or {}).get("result")) or [None])[0]
    if not result:
        raise ValueError(f"no chart result for {symbol}")
    meta = result.get("meta") or {}
    quote_data = (((result.get("indicators") or {}).get("quote")) or [{}])[0]
    points = [
        float(value) for value in quote_data.get("close") or [] if value is not None
    ]
    price = meta.get("regularMarketPrice")
    previous = meta.get("previousClose") or meta.get("chartPreviousClose")
    change = meta.get("regularMarketChangePercent")
    if change is None and price is not None and previous:
        change = (float(price) - float(previous)) / float(previous) * 100
    return StockSnapshot(
        symbol=symbol,
        label=label,
        price=float(price) if price is not None else (points[-1] if points else None),
        change_percent=float(change) if change is not None else None,
        points=points[-40:],
        available=price is not None or bool(points),
    )


def unavailable_stock(symbol: str, label: str) -> StockSnapshot:
    return StockSnapshot(symbol=symbol, label=label)
