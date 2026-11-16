import pytest

from app.rag.image_validation import ImageValidationError, validate_image


def png(width: int, height: int) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00\x00\x00\x00\x00"
    )


def test_png_dimensions_are_bounded() -> None:
    assert validate_image(png(100, 50), "image/png").width == 100
    with pytest.raises(ImageValidationError):
        validate_image(png(100_000, 100_000), "image/png")


def test_rejects_mismatched_type_and_oversized_file() -> None:
    with pytest.raises(ImageValidationError):
        validate_image(png(1, 1), "image/jpeg")
    with pytest.raises(ImageValidationError):
        validate_image(png(1, 1) + b"x" * (2 * 1024 * 1024), "image/png")


def test_jpeg_dimensions() -> None:
    frame = b"\xff\xc0\x00\x11\x08\x00\x10\x00\x20" + b"\x00" * 10
    image = b"\xff\xd8" + frame + b"\xff\xd9"
    assert validate_image(image, "image/jpeg").height == 16
    with pytest.raises(ImageValidationError):
        validate_image(b"\xff\xd8bad\xff\xd9", "image/jpeg")
