from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings.from_env(
        {
            "TZ": "Asia/Shanghai",
            "OUTPUT_DIR": str(tmp_path),
            "WEATHER_LOCATION": "上海",
            "WEATHER_LATITUDE": "31.2304",
            "WEATHER_LONGITUDE": "121.4737",
            "MARKET_INDEX_SYMBOL": "000001.SS",
            "MARKET_INDEX_LABEL": "上证指数",
            "STOCK_SYMBOLS": "601727.SS,600021.SS",
            "STOCK_LABELS": "上海电气,上海电力",
            "NEWS_API_BASE_URL": "",
            "NEWS_LABEL": "新浪 · 快讯",
            "AIRPAGE_ENABLED": "false",
        }
    )
