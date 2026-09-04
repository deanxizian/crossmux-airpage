from __future__ import annotations

from app.providers.news import fetch_news


class StubResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "source": "sina_7x24",
            "stale": False,
            "items": [
                {
                    "content": "【第一条快讯】这里是较长的详细内容",
                    "category_label": "A股",
                    "published_at": "2026-09-04T04:49:00Z",
                },
                {"content": "第二条快讯。", "source": "sina_7x24"},
                {"content": "第三条快讯"},
                {"content": "第四条快讯"},
            ],
        }


class StubClient:
    def get(
        self,
        url: str,
        params: dict[str, object],
        headers: dict[str, str],
    ) -> StubResponse:
        assert url == "https://news.example/api/v1/news/latest"
        assert params == {"category": "0", "limit": 3}
        assert headers["Accept"] == "application/json"
        return StubResponse()


def test_fetch_news_reads_sina_compatible_api_and_extracts_headlines(settings) -> None:
    settings = settings.__class__.from_env(
        {
            "NEWS_API_BASE_URL": "https://news.example/api/v1/news",
            "NEWS_CATEGORY": "0",
            "NEWS_LABEL": "新浪快讯",
            "NEWS_ITEMS": "3",
        }
    )
    news = fetch_news(settings, StubClient())  # type: ignore[arg-type]

    assert news.available
    assert news.label == "新浪快讯"
    assert [item.title for item in news.items] == [
        "第一条快讯",
        "第二条快讯",
        "第三条快讯",
    ]
