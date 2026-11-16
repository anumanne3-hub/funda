from subprocess import CompletedProcess, TimeoutExpired

import pytest

from app.rag import image_ocr
from app.rag.image_ocr import ImageOcrError, extract_image_text


def png() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR"
        + (100).to_bytes(4, "big") * 2
        + b"\x08\x02\x00\x00\x00\x00\x00\x00\x00"
    )


def test_image_ocr_preserves_image_location(monkeypatch):
    monkeypatch.setattr(
        image_ocr.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(args, 0, b"Earth has one moon.\n", b""),
    )
    segments = extract_image_text(png(), "image/png")
    assert segments[0].text == "Earth has one moon.\n"
    assert segments[0].location.section == "Image"


def test_image_ocr_fails_closed_on_timeout(monkeypatch):
    def timeout(*args, **kwargs):
        raise TimeoutExpired("tesseract", 45)

    monkeypatch.setattr(image_ocr.subprocess, "run", timeout)
    with pytest.raises(ImageOcrError):
        extract_image_text(png(), "image/png")


def test_image_ocr_retries_sparse_text_when_default_finds_nothing(monkeypatch):
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        output = b"Visible words\n" if "--psm" in command else b""
        return CompletedProcess(command, 0, output, b"")

    monkeypatch.setattr(image_ocr.subprocess, "run", run)
    segments = extract_image_text(png(), "image/png")
    assert segments[0].text == "Visible words\n"
    assert len(commands) == 2
    assert commands[1][-2:] == ["--psm", "11"]
