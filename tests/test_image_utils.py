"""Tests for image_utils.py — image resizing and encoding for Bedrock."""

import io

import pytest
from PIL import Image

from clean_grocery_bot.image_utils import _MAX_BYTES, _MAX_DIMENSION, prepare_image_for_bedrock


def _make_image(width: int, height: int, fmt: str = "JPEG") -> bytes:
    """Create a minimal test image of the given dimensions."""
    img = Image.new("RGB", (width, height), color=(128, 200, 50))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _make_rgba_image(width: int, height: int) -> bytes:
    """Create a PNG image with an alpha channel."""
    img = Image.new("RGBA", (width, height), color=(128, 200, 50, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_small_image_passes_through() -> None:
    raw = _make_image(800, 600)
    result_bytes, fmt = prepare_image_for_bedrock(raw)
    assert fmt == "jpeg"
    # Should be re-encoded (may differ in size) but still valid JPEG
    img = Image.open(io.BytesIO(result_bytes))
    assert img.format == "JPEG"
    assert img.size[0] <= _MAX_DIMENSION
    assert img.size[1] <= _MAX_DIMENSION


def test_large_image_is_downscaled() -> None:
    raw = _make_image(5000, 3000)
    result_bytes, fmt = prepare_image_for_bedrock(raw)
    assert fmt == "jpeg"
    img = Image.open(io.BytesIO(result_bytes))
    assert max(img.size) <= _MAX_DIMENSION
    # Aspect ratio preserved: 5000:3000 = 5:3
    assert abs(img.size[0] / img.size[1] - 5 / 3) < 0.02


def test_tall_image_is_downscaled() -> None:
    raw = _make_image(1000, 4000)
    result_bytes, _fmt = prepare_image_for_bedrock(raw)
    img = Image.open(io.BytesIO(result_bytes))
    assert max(img.size) <= _MAX_DIMENSION
    assert img.size[1] == _MAX_DIMENSION


def test_output_is_always_jpeg() -> None:
    raw_png = _make_image(400, 300, fmt="PNG")
    result_bytes, fmt = prepare_image_for_bedrock(raw_png)
    assert fmt == "jpeg"
    img = Image.open(io.BytesIO(result_bytes))
    assert img.format == "JPEG"


def test_rgba_image_is_converted_to_rgb() -> None:
    raw = _make_rgba_image(400, 300)
    result_bytes, fmt = prepare_image_for_bedrock(raw)
    assert fmt == "jpeg"
    img = Image.open(io.BytesIO(result_bytes))
    assert img.mode == "RGB"


def test_output_fits_within_size_limit() -> None:
    raw = _make_image(2000, 2000)
    result_bytes, _ = prepare_image_for_bedrock(raw)
    assert len(result_bytes) <= _MAX_BYTES


def test_corrupt_bytes_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Could not decode image"):
        prepare_image_for_bedrock(b"this is not an image")


def test_empty_bytes_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Could not decode image"):
        prepare_image_for_bedrock(b"")


def test_exact_max_dimension_not_resized() -> None:
    raw = _make_image(_MAX_DIMENSION, 1000)
    result_bytes, _ = prepare_image_for_bedrock(raw)
    img = Image.open(io.BytesIO(result_bytes))
    assert img.size[0] == _MAX_DIMENSION
