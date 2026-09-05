from __future__ import annotations

import asyncio

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

    async def send() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), follow_redirects=True
        ) as client:
            await push_bmp(client, device, b"test")

    with pytest.raises(AirPageError, match="HTTP 307"):
        asyncio.run(send())

    assert requested_urls == [
        "https://airpage.crossmux.cn/api/device/Abcdefghijk_1234/push"
    ]


def send_response(response: httpx.Response):
    async def send():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: response)
        ) as client:
            return await push_bmp(
                client,
                AirPageDevice(
                    "https://airpage.example.invalid", "0123456789abcdef", 528, 792
                ),
                b"test",
            )

    return asyncio.run(send())


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json={"ok": False}),
        httpx.Response(200, text="<html>error</html>"),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={}),
        httpx.Response(200, json={"ok": "false", "bytes": 4, "refreshed": True}),
        httpx.Response(200, json={"ok": True, "bytes": 4, "refreshed": "false"}),
        httpx.Response(200, json={"ok": True, "bytes": 4}),
        httpx.Response(200, json={"ok": True, "bytes": True, "refreshed": True}),
        httpx.Response(200, json={"ok": True, "bytes": 3, "refreshed": True}),
        httpx.Response(500, json={"ok": False}),
    ],
)
def test_rejects_business_failure_and_malformed_success(response) -> None:
    with pytest.raises(AirPageError):
        send_response(response)


@pytest.mark.parametrize("refresh", [True, False])
def test_upload_and_refresh_are_separate(refresh) -> None:
    result = send_response(
        httpx.Response(200, json={"ok": True, "bytes": 4, "refreshed": refresh})
    )
    assert result["uploaded"] is True
    assert result["refresh_requested"] is refresh
    assert result["manual_refresh"] is not refresh
    assert result["display_updated"] is None


def test_404_retries_once_and_requires_manual_refresh() -> None:
    requests = []

    def handler(request):
        requests.append(request)
        return (
            httpx.Response(404)
            if request.url.path.endswith("/push")
            else httpx.Response(200, json={"ok": True, "bytes": 4})
        )

    async def send():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await push_bmp(
                client,
                AirPageDevice(
                    "https://airpage.example.invalid", "0123456789abcdef", 528, 792
                ),
                b"test",
            )

    result = asyncio.run(send())
    assert len(requests) == 2
    assert requests[1].url.path.endswith("/image")
    assert b"test" in requests[0].content and b"test" in requests[1].content
    assert result["uploaded"] and result["manual_refresh"]
    assert not result["refresh_requested"]
