"""Bounded image checks before sending private uploads to an OCR provider."""

from dataclasses import dataclass

MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000


class ImageValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ValidatedImage:
    media_type: str
    width: int
    height: int


def validate_image(content: bytes, media_type: str) -> ValidatedImage:
    """Check PNG/JPEG headers and dimensions before full decoding by an extractor."""
    if not content or len(content) > MAX_IMAGE_BYTES:
        raise ImageValidationError("Image size is invalid")
    if media_type == "image/png":
        if len(content) < 33 or content[:8] != b"\x89PNG\r\n\x1a\n":
            raise ImageValidationError("Invalid PNG signature")
        if content[12:16] != b"IHDR" or int.from_bytes(content[8:12], "big") != 13:
            raise ImageValidationError("Invalid PNG header")
        width = int.from_bytes(content[16:20], "big")
        height = int.from_bytes(content[20:24], "big")
    elif media_type == "image/jpeg":
        if not content.startswith(b"\xff\xd8") or not content.endswith(b"\xff\xd9"):
            raise ImageValidationError("Invalid JPEG markers")
        width, height = _jpeg_dimensions(content)
    else:
        raise ImageValidationError("Unsupported image type")
    if width < 1 or height < 1 or width * height > MAX_IMAGE_PIXELS:
        raise ImageValidationError("Image dimensions exceed limit")
    return ValidatedImage(media_type, width, height)


def _jpeg_dimensions(content: bytes) -> tuple[int, int]:
    index = 2
    while index + 4 <= len(content) - 2:
        if content[index] != 0xFF:
            raise ImageValidationError("Invalid JPEG segment")
        while index < len(content) and content[index] == 0xFF:
            index += 1
        if index >= len(content):
            break
        marker = content[index]
        index += 1
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if index + 2 > len(content):
            break
        length = int.from_bytes(content[index : index + 2], "big")
        if length < 2 or index + length > len(content):
            raise ImageValidationError("Invalid JPEG segment length")
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if length < 7:
                raise ImageValidationError("Invalid JPEG frame")
            return (
                int.from_bytes(content[index + 5 : index + 7], "big"),
                int.from_bytes(content[index + 3 : index + 5], "big"),
            )
        index += length
    raise ImageValidationError("JPEG dimensions not found")
