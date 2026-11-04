import pytest

from app.rag.chunking import chunk_text
from app.rag.extract_text import MAX_TEXT_CHARS, ExtractionError, extract_text


def test_html_extraction_preserves_sections_and_excludes_hidden_content():
    html = (
        b"<h1>Overview</h1><p>First &amp; second.</p>"
        b"<script>ignore secret</script><h2>Details</h2>"
        b"<p>Useful <b>facts</b> here.</p>"
    )
    sections = extract_text(html, "text/html")
    assert [item.location.section for item in sections] == ["Overview", "Details"]
    assert [item.text for item in sections] == ["First & second.", "Useful facts here."]
    assert chunk_text(sections[1])[0].location.section == "Details"


def test_text_extraction_limits_and_utf8():
    assert extract_text(b"hello", "text/plain")[0].text == "hello"
    assert extract_text(b"# Heading", "text/markdown")[0].text == "# Heading"
    with pytest.raises(ExtractionError):
        extract_text(b"\xff", "text/plain")
    with pytest.raises(ExtractionError):
        extract_text(b"x" * (MAX_TEXT_CHARS + 1), "text/plain")
    with pytest.raises(ExtractionError):
        extract_text(b"hello", "application/pdf")
