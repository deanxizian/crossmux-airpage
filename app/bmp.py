from __future__ import annotations

import struct
from io import BytesIO

from PIL import Image

GRAY_LEVELS = (0, 85, 170, 255)


def quantize_gray4(image: Image.Image) -> Image.Image:
    """Quantize to the exact four grayscale values supported by AirPage."""
    gray = image.convert("L")
    table = [
        min(GRAY_LEVELS, key=lambda level: abs(level - value)) for value in range(256)
    ]
    return gray.point(table)


def encode_gray4_bmp(image: Image.Image) -> bytes:
    """Encode a bottom-up, 2-bit indexed BMP with a four-entry BGRA palette."""
    image = quantize_gray4(image)
    width, height = image.size
    source = image.tobytes()
    row_bytes = (width + 3) // 4
    row_padded = (row_bytes + 3) & ~3
    pixels = bytearray(row_padded * height)

    for out_row, y in enumerate(range(height - 1, -1, -1)):
        source_offset = y * width
        dest_offset = out_row * row_padded
        for x in range(width):
            index = source[source_offset + x] // 85
            pixels[dest_offset + x // 4] |= index << (6 - 2 * (x % 4))

    palette = b"".join(
        struct.pack("<BBBB", level, level, level, 0) for level in GRAY_LEVELS
    )
    pixel_offset = 14 + 40 + len(palette)
    file_size = pixel_offset + len(pixels)
    file_header = struct.pack("<2sIHHI", b"BM", file_size, 0, 0, pixel_offset)
    info_header = struct.pack(
        "<IiiHHIIiiII",
        40,
        width,
        height,
        1,
        2,
        0,
        len(pixels),
        2835,
        2835,
        4,
        4,
    )
    return file_header + info_header + palette + bytes(pixels)


def png_bytes(image: Image.Image) -> bytes:
    buffer = BytesIO()
    quantize_gray4(image).save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
