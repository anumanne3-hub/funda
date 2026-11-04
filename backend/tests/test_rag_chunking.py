import pytest

from app.rag.chunking import chunk_text
from app.rag.contracts import ExtractedText, RetrievalScope, SourceLocation


def test_chunks_preserve_source_offsets_and_cover_original_text():
    text = "The lunar mission collected observations. " * 8
    location = SourceLocation(page=3)
    chunks = chunk_text(ExtractedText(text, location), max_chars=80, overlap_chars=10)
    assert len(chunks) > 1
    assert chunks[0].start_offset == 0
    assert chunks[-1].end_offset == len(text)
    for chunk in chunks:
        assert chunk.location == location
        assert chunk.text == text[chunk.start_offset : chunk.end_offset]
        assert len(chunk.text) <= 80
    for left, right in zip(chunks, chunks[1:], strict=False):
        assert right.start_offset <= left.end_offset


def test_chunking_rejects_invalid_limits_and_ignores_empty_text():
    source = ExtractedText("   ", SourceLocation())
    assert chunk_text(source) == []
    with pytest.raises(ValueError):
        chunk_text(source, max_chars=10, overlap_chars=10)


def test_unscoped_retrieval_and_invalid_locations_are_rejected():
    from uuid import uuid4

    with pytest.raises(ValueError):
        RetrievalScope(user_id=uuid4(), project_id=None, conversation_id=None)
    with pytest.raises(ValueError):
        SourceLocation(start_ms=20, end_ms=10)
