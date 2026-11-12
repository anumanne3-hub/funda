"""Bounded extraction for UTF-8 text, Markdown, HTML, and PDF sources."""

from html.parser import HTMLParser
from io import BytesIO

from pypdf import PdfReader

from app.rag.contracts import ExtractedText, SourceLocation

MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_TEXT_CHARS = 500_000
MAX_PDF_PAGES = 50
SKIP_TAGS = {"script", "style", "noscript", "template", "svg"}
BLOCK_TAGS = {"p", "div", "li", "br", "tr", "article", "section", "blockquote"}
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


class ExtractionError(Exception):
    pass


class _VisibleHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.sections: list[ExtractedText] = []
        self.heading_parts: list[str] = []
        self.heading_tag: str | None = None
        self.section: str | None = None
        self.hidden_depth = 0
        self.total_chars = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIP_TAGS:
            self.hidden_depth += 1
        if self.hidden_depth:
            return
        if tag in HEADING_TAGS:
            self.flush()
            self.heading_tag = tag
            self.heading_parts = []
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS:
            self.hidden_depth = max(0, self.hidden_depth - 1)
            return
        if self.hidden_depth:
            return
        if tag == self.heading_tag:
            self.section = " ".join("".join(self.heading_parts).split())[:500] or self.section
            self.heading_tag = None
            self.heading_parts = []
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.hidden_depth:
            return
        self.total_chars += len(data)
        if self.total_chars > MAX_TEXT_CHARS:
            raise ExtractionError("Extracted text exceeds limit")
        if self.heading_tag:
            self.heading_parts.append(data)
        else:
            self.parts.append(data)

    def flush(self) -> None:
        text = " ".join("".join(self.parts).split())
        if text:
            self.sections.append(ExtractedText(text, SourceLocation(section=self.section)))
        self.parts = []


def extract_text(content: bytes, media_type: str) -> list[ExtractedText]:
    if len(content) > MAX_INPUT_BYTES:
        raise ExtractionError("Source exceeds byte limit")
    if media_type == "application/pdf":
        if not content.startswith(b"%PDF-"):
            raise ExtractionError("Source is not a PDF")
        try:
            reader = PdfReader(BytesIO(content), strict=True)
            if reader.is_encrypted:
                raise ExtractionError("Encrypted PDFs are unsupported")
            page_count = len(reader.pages)
            if not 1 <= page_count <= MAX_PDF_PAGES:
                raise ExtractionError("PDF page count exceeds limit")
            sections: list[ExtractedText] = []
            total_chars = 0
            for page_number, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                total_chars += len(text)
                if total_chars > MAX_TEXT_CHARS:
                    raise ExtractionError("Extracted text exceeds limit")
                if text.strip():
                    sections.append(ExtractedText(text, SourceLocation(page=page_number)))
            return sections
        except ExtractionError:
            raise
        except Exception as exc:
            raise ExtractionError("PDF could not be extracted") from exc
    if media_type not in {"text/plain", "text/markdown", "text/html"}:
        raise ExtractionError("Unsupported media type")
    try:
        text = content.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as exc:
        raise ExtractionError("Source is not valid UTF-8") from exc
    if media_type != "text/html":
        if len(text) > MAX_TEXT_CHARS:
            raise ExtractionError("Extracted text exceeds limit")
        return [ExtractedText(text, SourceLocation())] if text.strip() else []
    parser = _VisibleHTML()
    parser.feed(text)
    parser.close()
    parser.flush()
    return parser.sections
