from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.config import Settings
from app.models import NewsItem, NewsSnapshot, SnapshotInfo
from app.validation import timestamp

NEWS_ACCEPT = "application/json"
SPACE_RE = re.compile(r"\s+")
BRACKET_HEADLINE_RE = re.compile(r"^【([^】]+)】")


def _clean_text(value: str) -> str:
    return SPACE_RE.sub(" ", value).strip()


def _headline(content: str) -> str:
    cleaned = _clean_text(content)
    match = BRACKET_HEADLINE_RE.match(cleaned)
    headline = match.group(1).strip() if match else cleaned
    return headline.rstrip("。；;")


def _parse_payload(payload: dict[str, Any], limit: int) -> list[NewsItem]:
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise TypeError("新闻 API 响应缺少 items")
    items: list[NewsItem] = []
    seen: set[str] = set()
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        content = raw_item.get("content")
        if not isinstance(content, str):
            continue
        title = _headline(content)
        if not title:
            continue
        fingerprint = title.casefold()
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        items.append(
            NewsItem(title=title, published_at=timestamp(raw_item.get("published_at")))
        )
        if len(items) >= limit:
            break
    if not items:
        raise ValueError("新闻 API 中没有可用快讯")
    return items


def _latest_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    return normalized if normalized.endswith("/latest") else f"{normalized}/latest"


async def fetch_news(settings: Settings, client: httpx.AsyncClient) -> NewsSnapshot:
    if not settings.news_api_base_url:
        return unavailable_news(settings)
    response = await client.get(
        _latest_url(settings.news_api_base_url),
        params={"category": settings.news_category, "limit": settings.news_items},
        headers={
            "Accept": NEWS_ACCEPT,
            "User-Agent": "CrossMux-AirPage/0.1",
        },
    )
    response.raise_for_status()
    try:
        payload = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("新闻 API 返回的不是有效 JSON") from exc
    if not isinstance(payload, dict):
        raise TypeError("新闻 API 返回格式无效")
    items = _parse_payload(payload, settings.news_items)
    stale = payload.get("stale", False)
    if not isinstance(stale, bool):
        raise TypeError("新闻 stale 必须是布尔值")
    published = [item.published_at for item in items if item.published_at is not None]
    return NewsSnapshot(
        label=settings.news_label,
        items=items,
        available=True,
        info=SnapshotInfo(
            data_at=max(published) if published else None,
            state="stale" if stale else "fresh",
        ),
    )


def unavailable_news(settings: Settings) -> NewsSnapshot:
    return NewsSnapshot(label=settings.news_label)
