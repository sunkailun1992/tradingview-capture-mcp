"""PNG checks and crops."""

from __future__ import annotations

import io
import struct
from pathlib import Path

from PIL import Image

from .errors import INVALID_ARGUMENT, CaptureError

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_size(data: bytes) -> tuple[int, int] | None:
    """Width and height from the IHDR chunk, or None when the bytes are not a PNG."""
    if len(data) < 24 or not data.startswith(PNG_SIGNATURE) or data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return (width, height) if width > 0 and height > 0 else None


def crop_png(path: Path, x: int, y: int, width: int, height: int) -> bytes:
    with Image.open(path) as image:
        if image.format != "PNG":
            raise CaptureError(INVALID_ARGUMENT, "the image is not a PNG", {"path": path.name})
        image_width, image_height = image.size
        if (
            x < 0
            or y < 0
            or width <= 0
            or height <= 0
            or x + width > image_width
            or y + height > image_height
        ):
            raise CaptureError(
                INVALID_ARGUMENT,
                "the crop box is outside the image",
                {"image": [image_width, image_height], "box": [x, y, width, height]},
            )
        buffer = io.BytesIO()
        image.crop((x, y, x + width, y + height)).save(buffer, format="PNG")
        return buffer.getvalue()
