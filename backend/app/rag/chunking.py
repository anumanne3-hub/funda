"""Bounded text chunking that preserves source locations and offsets."""

from app.rag.contracts import ExtractedText, TextChunk

CHUNKER_VERSION = "characters-v1"


def chunk_text(
    source: ExtractedText, *, max_chars: int = 1200, overlap_chars: int = 150
) -> list[TextChunk]:
    """Split one extracted source segment without crossing its provenance boundary.

    Offsets refer to the original extracted text. Whitespace is preserved so an
    auditor can map every chunk back to the source segment without guessing.
    """
    if max_chars < 1 or not 0 <= overlap_chars < max_chars:
        raise ValueError("overlap must be non-negative and smaller than max_chars")
    text = source.text
    if not text.strip():
        return []
    chunks: list[TextChunk] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            # Prefer a word boundary in the latter half, without risking no progress.
            boundary = text.rfind(" ", start + max_chars // 2, end)
            if boundary > start + overlap_chars:
                end = boundary + 1
        if text[start:end].strip():
            chunks.append(TextChunk(text[start:end], source.location, start, end))
        if end == len(text):
            break
        start = end - overlap_chars
    return chunks
