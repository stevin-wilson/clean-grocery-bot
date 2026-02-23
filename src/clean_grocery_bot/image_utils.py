"""Image preprocessing utilities for Bedrock multimodal input."""

from __future__ import annotations

import io
import logging

from PIL import Image
from PIL.Image import Resampling

logger = logging.getLogger(__name__)

_MAX_DIMENSION = 2000
_MAX_BYTES = 2_500_000  # 2.5 MB — safe margin under Bedrock's 3.75 MB post-base64 limit
_QUALITY_STEPS = (85, 75, 65)


def prepare_image_for_bedrock(raw_bytes: bytes) -> tuple[bytes, str]:
    """Resize and re-encode an image so it fits Bedrock Converse API limits.

    The image is downscaled (if needed) so the longest side is at most
    ``_MAX_DIMENSION`` pixels, then JPEG-compressed.  If the result still
    exceeds ``_MAX_BYTES``, the JPEG quality is reduced in steps until it fits.

    Args:
        raw_bytes: Raw image file bytes (any format Pillow can open).

    Returns:
        A ``(jpeg_bytes, "jpeg")`` tuple ready for the Bedrock image content block.

    Raises:
        ValueError: If *raw_bytes* cannot be decoded as an image.
    """
    try:
        img = Image.open(io.BytesIO(raw_bytes))
    except Exception as exc:
        raise ValueError("Could not decode image") from exc  # noqa: TRY003

    # Convert to RGB (handles PNG with alpha, palette modes, etc.)
    if img.mode != "RGB":
        img = img.convert("RGB")

    # Downscale if either dimension exceeds the limit
    width, height = img.size
    if width > _MAX_DIMENSION or height > _MAX_DIMENSION:
        scale = _MAX_DIMENSION / max(width, height)
        new_size = (int(width * scale), int(height * scale))
        logger.info("Resizing image from %dx%d to %dx%d", width, height, *new_size)
        img = img.resize(new_size, Resampling.LANCZOS)  # type: ignore[reportUnknownMemberType]

    # Encode as JPEG, reducing quality if needed to stay under size limit
    jpeg_bytes = b""
    for quality in _QUALITY_STEPS:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        jpeg_bytes = buf.getvalue()
        if len(jpeg_bytes) <= _MAX_BYTES:
            logger.debug("JPEG encoded at quality %d: %d bytes", quality, len(jpeg_bytes))
            return jpeg_bytes, "jpeg"

    # Last resort — already at lowest quality step
    logger.warning("Image still %d bytes after quality reduction", len(jpeg_bytes))
    return jpeg_bytes, "jpeg"
