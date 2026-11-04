"""Explicit boundaries between extraction, retrieval, and the future orchestrator."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class SourceLocation:
    """Location in the original source, carried through indexing into citations."""

    page: int | None = None
    section: str | None = None
    start_ms: int | None = None
    end_ms: int | None = None

    def __post_init__(self) -> None:
        if self.page is not None and self.page < 1:
            raise ValueError("page must be positive")
        if self.start_ms is not None and self.start_ms < 0:
            raise ValueError("start_ms must be non-negative")
        if self.end_ms is not None and (
            self.end_ms < 0 or (self.start_ms is not None and self.end_ms < self.start_ms)
        ):
            raise ValueError("end_ms must not precede start_ms")


@dataclass(frozen=True, slots=True)
class ExtractedText:
    text: str
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class TextChunk:
    text: str
    location: SourceLocation
    start_offset: int
    end_offset: int


@dataclass(frozen=True, slots=True)
class RetrievalScope:
    """The caller must establish ownership before creating a retrieval request."""

    user_id: UUID
    project_id: UUID | None
    conversation_id: UUID | None

    def __post_init__(self) -> None:
        if self.project_id is None and self.conversation_id is None:
            raise ValueError("retrieval requires a project or conversation scope")


@dataclass(frozen=True, slots=True)
class RetrievedEvidence:
    document_id: UUID
    document_version_id: UUID
    chunk_id: UUID
    title: str
    text: str
    location: SourceLocation
    source_url: str | None = None


class EmbeddingProvider(Protocol):
    model: str
    dimensions: int

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class RetrievalService(Protocol):
    async def search(
        self, scope: RetrievalScope, query: str, *, limit: int
    ) -> list[RetrievedEvidence]: ...
