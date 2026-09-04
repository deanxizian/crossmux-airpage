from __future__ import annotations

import httpx
import pytest

from app.airpage import AirPageDevice, AirPageError, parse_device_url, push_bmp


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


def test_push_does_not_follow_cross_origin_redirects() -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(
            307,
            headers={"Location": "https://evil.example/collect"},
            request=request,
        )

    device = AirPageDevice(
        origin="https://airpage.crossmux.cn",
        device_id="Abcdefghijk_1234",
        width=528,
        height=792,
    )
    with (
        httpx.Client(
            transport=httpx.MockTransport(handler),
            follow_redirects=True,
        ) as client,
        pytest.raises(AirPageError, match="HTTP 307"),
    ):
        push_bmp(client, device, b"test")

    assert requested_urls == [
        "https://airpage.crossmux.cn/api/device/Abcdefghijk_1234/push"
    ]
