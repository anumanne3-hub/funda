"""Prepare one website source for later embedding and atomic publication."""

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.rag.chunking import chunk_text
from app.rag.contracts import TextChunk
from app.rag.extract_text import ExtractionError, extract_text
from app.rag.web_sources import SourceFetchError, fetch_website

MAX_CHUNKS = 500


@dataclass(frozen=True, slots=True)
class PreparedSource:
    content_hash: str
    media_type: str
    original: bytes
    chunks: list[TextChunk]


class PreparationError(Exception):
    pass


async def prepare_website(
    url: str,
    allowed_urls: set[str],
    *,
    fetch: Callable[[str, set[str]], Awaitable[tuple[str, bytes]]] = fetch_website,
) -> PreparedSource:
    try:
        media_type, original = await fetch(url, allowed_urls)
        segments = extract_text(original, media_type)
    except (SourceFetchError, ExtractionError) as exc:
        raise PreparationError("Website could not be prepared") from exc
    chunks: list[TextChunk] = []
    for segment in segments:
        chunks.extend(chunk_text(segment))
        if len(chunks) > MAX_CHUNKS:
            raise PreparationError("Website has too many chunks")
    if not chunks:
        raise PreparationError("Website has no extractable text")
    return PreparedSource(
        content_hash=hashlib.sha256(original).hexdigest(),
        media_type=media_type,
        original=original,
        chunks=chunks,
    )
