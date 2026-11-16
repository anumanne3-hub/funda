"""Run real OCR in the ingestion runner, where Tesseract is installed."""

import shutil
from pathlib import Path

import pytest

from app.rag.image_ocr import extract_image_text


def test_tesseract_reads_real_png() -> None:
    if shutil.which("tesseract") is None:
        pytest.skip("Tesseract is not installed on this machine")
    content = (Path(__file__).parent / "fixtures" / "ocr_earth.png").read_bytes()
    segments = extract_image_text(content, "image/png")
    assert segments and "EARTH" in segments[0].text.upper()
    assert segments[0].location.section == "Image"
