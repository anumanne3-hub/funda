"""Prepare, embed, and atomically publish one claimed text document version."""

import hashlib
import json
import math
from asyncio import to_thread
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.models import Document, DocumentChunk, DocumentVersion, IngestionJob
from app.rag.chunking import chunk_text
from app.rag.contracts import EmbeddingProvider
from app.rag.extract_text import ExtractionError, extract_text
from app.rag.prepare import MAX_CHUNKS, PreparationError, PreparedSource, prepare_website
from app.rag.storage import StorageError, object_key
from app.rag.web_sources import fetch_website
from app.rag.worker import ProcessingError


class ObjectStorage(Protocol):
    def put(self, key: str, content: bytes, media_type: str) -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


class VectorWriter(Protocol):
    def __call__(self, db: Session, chunk_id: UUID, vector: list[float]) -> None: ...


class _AlreadyIndexed(Exception):
    pass


def write_pgvector(db: Session, chunk_id: UUID, vector: list[float]) -> None:
    if len(vector) != 2048 or not all(math.isfinite(value) for value in vector):
        raise ValueError("Invalid vector shape")
    db.execute(
        text(
            "UPDATE document_chunks "
            "SET embedding = CAST(:embedding AS extensions.vector(2048)) "
            "WHERE id = :chunk_id"
        ),
        {"embedding": json.dumps(vector, separators=(",", ":")), "chunk_id": chunk_id},
    )


class TextIngestionProcessor:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        storage: ObjectStorage,
        embeddings: EmbeddingProvider,
        *,
        allowed_urls: set[str],
        vector_writer: VectorWriter = write_pgvector,
        fetch: Callable[[str, set[str]], Awaitable[tuple[str, bytes]]] = fetch_website,
    ) -> None:
        self.session_factory = session_factory
        self.storage = storage
        self.embeddings = embeddings
        self.allowed_urls = allowed_urls
        self.vector_writer = vector_writer
        self.fetch = fetch

    async def __call__(self, job: IngestionJob) -> None:
        with self.session_factory() as db:
            document = db.scalar(
                select(Document)
                .join(IngestionJob, IngestionJob.document_id == Document.id)
                .where(
                    IngestionJob.id == job.id,
                    IngestionJob.user_id == Document.user_id,
                    Document.deleted_at.is_(None),
                )
            )
            if document is None:
                raise ProcessingError("DOCUMENT_UNAVAILABLE")
            document_id, user_id = document.id, document.user_id
            source_kind, source_key = document.source_kind, document.source_key
            upload_version = None
            if source_kind == "upload":
                upload_version = db.scalar(
                    select(DocumentVersion).where(DocumentVersion.document_id == document_id)
                )
                if (
                    upload_version is None
                    or not upload_version.storage_key
                    or not upload_version.media_type
                ):
                    raise ProcessingError("UPLOAD_VERSION_MISSING")
                upload_version_id = upload_version.id
                upload_path = upload_version.storage_key
                upload_type = upload_version.media_type
                upload_hash = upload_version.content_hash
        if source_kind == "website":
            try:
                prepared = await prepare_website(source_key, self.allowed_urls, fetch=self.fetch)
            except PreparationError as exc:
                raise ProcessingError("SOURCE_PREPARATION_FAILED", retryable=True) from exc
            version_id = uuid4()
            storage_path = object_key(user_id, document_id, version_id)
            needs_upload = True
        elif source_kind == "upload":
            try:
                original = await to_thread(self.storage.get, upload_path)
                if hashlib.sha256(original).hexdigest() != upload_hash:
                    raise ProcessingError("UPLOAD_HASH_MISMATCH")
                segments = extract_text(original, upload_type)
            except (StorageError, ExtractionError) as exc:
                raise ProcessingError("UPLOAD_PREPARATION_FAILED", retryable=True) from exc
            chunks = [chunk for segment in segments for chunk in chunk_text(segment)]
            if not chunks or len(chunks) > MAX_CHUNKS:
                raise ProcessingError("UPLOAD_CHUNKS_INVALID")
            prepared = PreparedSource(upload_hash, upload_type, original, chunks)
            version_id = upload_version_id
            storage_path = upload_path
            needs_upload = False
        else:
            raise ProcessingError("SOURCE_KIND_UNSUPPORTED")
        with self.session_factory() as db:
            existing = db.scalar(
                select(DocumentVersion).where(
                    DocumentVersion.document_id == document_id,
                    DocumentVersion.content_hash == prepared.content_hash,
                )
            )
            if existing is not None and existing.status == "ready":
                return
        vectors = await self.embeddings.embed_documents([chunk.text for chunk in prepared.chunks])
        if len(vectors) != len(prepared.chunks) or any(
            len(vector) != self.embeddings.dimensions for vector in vectors
        ):
            raise ProcessingError("EMBEDDING_SHAPE_INVALID", retryable=True)
        uploaded = False
        try:
            if needs_upload:
                await to_thread(
                    self.storage.put, storage_path, prepared.original, prepared.media_type
                )
                uploaded = True
            with self.session_factory() as db, db.begin():
                locked = db.scalar(
                    select(Document).where(Document.id == document_id).with_for_update()
                )
                if locked is None or locked.deleted_at is not None or locked.user_id != user_id:
                    raise ProcessingError("DOCUMENT_UNAVAILABLE")
                existing = db.scalar(
                    select(DocumentVersion).where(
                        DocumentVersion.document_id == document_id,
                        DocumentVersion.content_hash == prepared.content_hash,
                    )
                )
                if existing is not None and existing.status == "ready":
                    raise _AlreadyIndexed
                if existing is not None and existing.id != version_id:
                    raise ProcessingError("VERSION_INCOMPLETE")
                version = existing or DocumentVersion(
                    id=version_id,
                    document_id=document_id,
                    content_hash=prepared.content_hash,
                    storage_key=storage_path,
                    media_type=prepared.media_type,
                    status="indexing",
                )
                if existing is None:
                    db.add(version)
                    db.flush()
                db.execute(
                    delete(DocumentChunk).where(DocumentChunk.document_version_id == version.id)
                )
                rows = [
                    DocumentChunk(
                        document_version_id=version.id,
                        ordinal=index,
                        content=chunk.text,
                        page=chunk.location.page,
                        section=chunk.location.section,
                        start_ms=chunk.location.start_ms,
                        end_ms=chunk.location.end_ms,
                        start_offset=chunk.start_offset,
                        end_offset=chunk.end_offset,
                    )
                    for index, chunk in enumerate(prepared.chunks)
                ]
                db.add_all(rows)
                db.flush()
                for row, vector in zip(rows, vectors, strict=True):
                    self.vector_writer(db, row.id, vector)
                version.embedding_model = self.embeddings.model
                version.embedding_dimensions = self.embeddings.dimensions
                version.status = "ready"
                version.published_at = datetime.now(UTC)
        except _AlreadyIndexed:
            if uploaded:
                with suppress(StorageError):
                    await to_thread(self.storage.delete, storage_path)
            return
        except Exception:
            if uploaded:
                with suppress(StorageError):
                    await to_thread(self.storage.delete, storage_path)
            raise
