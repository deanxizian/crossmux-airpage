from __future__ import annotations

import pytest

from app.airpage import AirPageError, parse_device_url


def test_parse_x3_device_url() -> None:
    device = parse_device_url(
        "https://airpage.crossmux.cn/?id=Abcdefghijk_1234&w=528&h=792&mode=gray4",
        ("airpage.crossmux.cn",),
    )
    assert (device.width, device.height) == (528, 792)
    assert device.masked_id == "Abc***34"


def test_rejects_untrusted_airpage_host() -> None:
    with pytest.raises(AirPageError, match="白名单"):
        parse_device_url(
            "https://evil.example/?id=Abcdefghijk_1234&w=528&h=792&mode=gray4",
            ("airpage.crossmux.cn",),
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://airpage.crossmux.cn/?id=Abcdefghijk_1234&w=528&h=792&mode=gray4",
        "https://airpage.crossmux.cn/?id=Abcdefghijk_1234&w=528&h=792&mode=mono",
        "https://airpage.crossmux.cn/?id=Abcdefghijk_1234&mode=gray4",
    ],
)
def test_rejects_incomplete_or_insecure_device_url(url: str) -> None:
    with pytest.raises(AirPageError):
        parse_device_url(url, ("airpage.crossmux.cn",))
