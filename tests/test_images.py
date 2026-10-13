import io

import pytest
from helpers import png_bytes
from PIL import Image

from tradingview_capture_mcp.errors import CaptureError
from tradingview_capture_mcp.images import crop_png, png_size


def test_png_size_reads_the_header():
    assert png_size(png_bytes(12, 7)) == (12, 7)
    assert png_size(b"not a png at all, just some text") is None
    assert png_size(b"") is None


def test_crop_returns_the_requested_region(tmp_path):
    path = tmp_path / "image.png"
    image = Image.new("RGB", (10, 8), (0, 0, 0))
    image.putpixel((3, 2), (255, 0, 0))
    image.save(path)
    with Image.open(io.BytesIO(crop_png(path, 3, 2, 4, 5))) as cropped:
        assert cropped.size == (4, 5)
        assert cropped.getpixel((0, 0))[:3] == (255, 0, 0)


@pytest.mark.parametrize("box", [(0, 0, 11, 1), (-1, 0, 2, 2), (0, 0, 0, 2), (9, 7, 2, 2)])
def test_crop_rejects_boxes_outside_the_image(tmp_path, box):
    path = tmp_path / "image.png"
    Image.new("RGB", (10, 8)).save(path)
    with pytest.raises(CaptureError) as err:
        crop_png(path, *box)
    assert err.value.code == "INVALID_ARGUMENT"


def test_crop_rejects_other_formats(tmp_path):
    path = tmp_path / "image.png"
    Image.new("RGB", (10, 8)).save(path, format="JPEG")
    with pytest.raises(CaptureError) as err:
        crop_png(path, 0, 0, 2, 2)
    assert err.value.code == "INVALID_ARGUMENT"
