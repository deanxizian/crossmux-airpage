from __future__ import annotations

from urllib.parse import quote

import httpx

from app.config import Settings
from app.models import SnapshotInfo, StockSnapshot
from app.validation import epoch_timestamp, number

YAHOO_CHART_URL = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"


async def fetch_stock(
    settings: Settings, client: httpx.AsyncClient, symbol: str, label: str
) -> StockSnapshot:
    response = await client.get(
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
    raw_points = quote_data.get("close") or []
    if not isinstance(raw_points, list):
        raise TypeError("行情 close 必须是数组")
    points = [value for raw in raw_points if (value := number(raw)) is not None]
    price = number(meta.get("regularMarketPrice"))
    previous = number(meta.get("previousClose")) or number(
        meta.get("chartPreviousClose")
    )
    change = number(meta.get("regularMarketChangePercent"))
    if change is None and price is not None and previous:
        change = number((price - previous) / previous * 100)
    if price is None and not points:
        raise ValueError("行情没有可用价格")
    return StockSnapshot(
        symbol=symbol,
        label=label,
        price=price if price is not None else points[-1],
        change_percent=change,
        points=points[-40:],
        available=True,
        info=SnapshotInfo(
            data_at=epoch_timestamp(meta.get("regularMarketTime")), state="fresh"
        ),
    )


def unavailable_stock(symbol: str, label: str) -> StockSnapshot:
    return StockSnapshot(symbol=symbol, label=label)
