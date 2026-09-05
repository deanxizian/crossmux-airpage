from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

import httpx

DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16}$")


class AirPageError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AirPageDevice:
    origin: str
    device_id: str
    width: int
    height: int

    @property
    def masked_id(self) -> str:
        return f"{self.device_id[:3]}***{self.device_id[-2:]}"


def parse_device_url(
    value: str,
    trusted_hosts: tuple[str, ...],
) -> AirPageDevice:
    parsed = urlsplit(value.strip())
    if parsed.scheme != "https" or not parsed.hostname:
        raise AirPageError("AIRPAGE_DEVICE_URL 必须是有效的 HTTPS 地址")
    if (
        parsed.username
        or parsed.password
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise AirPageError("AIRPAGE_DEVICE_URL 包含不支持的地址组成部分")
    if parsed.hostname.lower() not in {host.lower() for host in trusted_hosts}:
        raise AirPageError("AirPage 域名不在 AIRPAGE_TRUSTED_HOSTS 白名单中")
    query = parse_qs(parsed.query)
    device_id = (query.get("id") or [""])[0]
    if not DEVICE_ID_RE.fullmatch(device_id):
        raise AirPageError("AirPage 设备 ID 应为 16 位字母、数字、下划线或连字符")

    device_type = (query.get("type") or [""])[0].lower()
    if device_type in {"x3", "xteink-x3"}:
        width, height = 528, 792
    elif device_type in {"x4", "xteink-x4"}:
        width, height = 480, 800
    else:
        if (query.get("mode") or [""])[0] != "gray4":
            raise AirPageError("AirPage 设备模式必须是 gray4")
        if "w" not in query or "h" not in query:
            raise AirPageError("AirPage 设备链接缺少宽高参数")
        try:
            width = int(query["w"][0])
            height = int(query["h"][0])
        except (TypeError, ValueError) as exc:
            raise AirPageError("AirPage 宽高参数无效") from exc
    if width < 128 or height < 128:
        raise AirPageError("AirPage 宽高参数过小")
    row_bytes = ((width + 3) // 4 + 3) & ~3
    if 70 + row_bytes * height > 512 * 1024:
        raise AirPageError("2-bit BMP 会超过 AirPage 的 512 KiB 上限")
    origin = f"https://{parsed.netloc}"
    return AirPageDevice(origin=origin, device_id=device_id, width=width, height=height)


async def push_bmp(
    client: httpx.AsyncClient, device: AirPageDevice, bmp: bytes
) -> dict[str, object]:
    files = {"image": ("airpage.bmp", bmp, "image/bmp")}
    try:
        response = await client.post(
            f"{device.origin}/api/device/{device.device_id}/push",
            files=files,
            follow_redirects=False,
        )
        manual_refresh = False
        if response.status_code == 404:
            response = await client.post(
                f"{device.origin}/api/device/{device.device_id}/image",
                files=files,
                follow_redirects=False,
            )
            manual_refresh = True
    except httpx.RequestError as exc:
        raise AirPageError("无法连接 AirPage 服务") from exc
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise AirPageError(f"AirPage 推送失败（HTTP {response.status_code}）") from exc
    try:
        payload = response.json()
    except (ValueError, UnicodeDecodeError) as exc:
        raise AirPageError("AirPage 返回的不是有效 JSON") from exc
    if not isinstance(payload, dict):
        raise AirPageError("AirPage 响应必须是 JSON 对象")
    if payload.get("ok") is False:
        raise AirPageError("AirPage 服务端拒绝了上传")
    if payload.get("ok") is not True:
        raise AirPageError("AirPage 响应缺少有效的成功标志")
    uploaded_bytes = payload.get("bytes")
    if type(uploaded_bytes) is not int or uploaded_bytes != len(bmp):
        raise AirPageError("AirPage 返回的上传大小与图片不一致")
    if not manual_refresh and type(payload.get("refreshed")) is not bool:
        raise AirPageError("AirPage 响应缺少有效的刷新通知状态")
    refresh_requested = not manual_refresh and payload["refreshed"]
    return {
        "ok": True,
        "uploaded": True,
        "bytes": uploaded_bytes,
        "refresh_requested": refresh_requested,
        "display_updated": None,
        "manual_refresh": not refresh_requested,
        "http_status": response.status_code,
        "device": device.masked_id,
    }
