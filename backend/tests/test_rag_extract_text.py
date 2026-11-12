from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.rag.chunking import chunk_text
from app.rag.extract_text import MAX_PDF_PAGES, MAX_TEXT_CHARS, ExtractionError, extract_text


def sample_pdf(*, pages: int = 2, encrypted: bool = False) -> bytes:
    writer = PdfWriter()
    for index in range(pages):
        page = writer.add_blank_page(width=300, height=300)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        font_ref = writer._add_object(font)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 20 250 Td (Page {index + 1}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("secret")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_pdf_extraction_preserves_pages_and_rejects_invalid_files():
    sections = extract_text(sample_pdf(), "application/pdf")
    assert [(item.text.strip(), item.location.page) for item in sections] == [
        ("Page 1", 1),
        ("Page 2", 2),
    ]
    with pytest.raises(ExtractionError):
        extract_text(b"%PDF-not a real file", "application/pdf")
    with pytest.raises(ExtractionError):
        extract_text(sample_pdf(encrypted=True), "application/pdf")
    with pytest.raises(ExtractionError):
        extract_text(sample_pdf(pages=MAX_PDF_PAGES + 1), "application/pdf")


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
