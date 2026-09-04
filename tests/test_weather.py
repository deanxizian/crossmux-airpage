from __future__ import annotations

from app.providers.weather import fetch_weather


class StubResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "daily": {
                "time": [
                    "2026-09-04",
                    "2026-09-05",
                    "2026-09-06",
                    "2026-09-07",
                    "2026-09-08",
                    "2026-09-09",
                ],
                "weather_code": [2, 2, 61, 0, 2, 95],
                "temperature_2m_max": [31, 32, 29, 31, 30, 27],
                "temperature_2m_min": [20, 23, 21, 20, 21, 20],
                "precipitation_probability_max": [10, 20, 60, 10, 20, 70],
            },
        }


class StubClient:
    def __init__(self) -> None:
        self.params: dict[str, object] = {}

    def get(self, _url: str, params: dict[str, object]) -> StubResponse:
        self.params = params
        return StubResponse()


def test_fetch_weather_keeps_today_and_next_four_days(settings) -> None:
    client = StubClient()
    weather = fetch_weather(settings, client)  # type: ignore[arg-type]

    assert client.params["forecast_days"] == 5
    assert len(weather.forecasts) == 5
    assert weather.forecasts[0].date.isoformat() == "2026-09-04"
    assert weather.forecasts[0].description == "多云"
    assert weather.forecasts[2].description == "小雨"
    assert weather.forecasts[-1].precipitation_probability == 20
