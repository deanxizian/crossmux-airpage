from __future__ import annotations

import struct

from PIL import Image

from app.bmp import encode_gray4_bmp, quantize_gray4


def test_quantize_uses_exact_four_levels() -> None:
    image = Image.new("L", (256, 1))
    image.putdata(range(256))
    quantized = quantize_gray4(image)
    assert set(quantized.tobytes()) == {0, 85, 170, 255}


def test_airpage_bmp_header_and_size() -> None:
    image = Image.new("L", (528, 792), 255)
    payload = encode_gray4_bmp(image)
    assert payload[:2] == b"BM"
    assert struct.unpack_from("<I", payload, 2)[0] == len(payload)
    assert struct.unpack_from("<I", payload, 10)[0] == 70
    assert struct.unpack_from("<i", payload, 18)[0] == 528
    assert struct.unpack_from("<i", payload, 22)[0] == 792
    assert struct.unpack_from("<H", payload, 28)[0] == 2
    assert len(payload) == 70 + 132 * 792
    assert len(payload) < 512 * 1024
