"""Run bounded local OCR on one private image in the ingestion worker."""

import subprocess

from app.rag.contracts import ExtractedText, SourceLocation
from app.rag.image_validation import ImageValidationError, validate_image

MAX_OCR_CHARS = 100_000
OCR_TIMEOUT_SECONDS = 45


class ImageOcrError(Exception):
    pass


def _run_ocr(content: bytes, *, sparse: bool = False) -> str:
    command = ["tesseract", "stdin", "stdout", "-l", "eng"]
    if sparse:
        command.extend(["--psm", "11"])
    try:
        result = subprocess.run(
            command,
            input=content,
            capture_output=True,
            timeout=OCR_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ImageOcrError("OCR unavailable or timed out") from exc
    if result.returncode != 0 or len(result.stdout) > MAX_OCR_CHARS * 4:
        raise ImageOcrError("OCR could not extract image")
    try:
        text = result.stdout.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ImageOcrError("OCR returned invalid text") from exc
    if len(text) > MAX_OCR_CHARS:
        raise ImageOcrError("OCR text exceeds limit")
    return text


def extract_image_text(content: bytes, media_type: str) -> list[ExtractedText]:
    try:
        validate_image(content, media_type)
    except ImageValidationError as exc:
        raise ImageOcrError("Invalid image") from exc
    text = _run_ocr(content)
    if not text.strip():
        text = _run_ocr(content, sparse=True)
    return [ExtractedText(text, SourceLocation(section="Image"))] if text.strip() else []
