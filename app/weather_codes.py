"""Chinese display names for Open-Meteo WMO codes; see docs/weather-terms.md."""

from __future__ import annotations

# Follow Apple Weather's Chinese terminology where meanings match, while keeping
# WMO rain/snow intensity and hazardous conditions that its icon guide groups.
WEATHER_DESCRIPTIONS = {
    0: "晴朗无云",
    1: "大部晴朗无云",
    2: "局部多云",
    3: "多云",
    45: "雾",
    48: "雾伴雾凇",
    51: "微雨",
    53: "微雨",
    55: "微雨",
    56: "冻细雨",
    57: "冻细雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "冻雨",
    67: "冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "米雪",
    80: "阵雨",
    81: "阵雨",
    82: "强阵雨",
    85: "阵雪",
    86: "强阵雪",
    95: "雷暴雨",
    96: "雷暴伴雹",
    99: "雷暴伴雹",
}


def weather_description(code: int | None) -> str:
    """Resolve display text from the code, never from a persisted old label."""
    return WEATHER_DESCRIPTIONS.get(code, "未知")
