"""Retryable cleanup of explicitly deleted document originals and index data."""

import sys
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import Document, DocumentChunk, DocumentVersion, IngestionJob, StorageDeletion
from app.rag.deletion_queue import enqueue_document_storage
from app.rag.storage import PrivateStorage, StorageError

DELETION_GRACE = timedelta(hours=1)
MAX_CLEANUP_DOCUMENTS = 20


class DeletingStorage(Protocol):
    def delete(self, key: str) -> None: ...


def deleted_document_ids(db: Session, *, now: datetime | None = None) -> list[UUID]:
    cutoff = (now or datetime.now(UTC)) - DELETION_GRACE
    return list(
        db.scalars(
            select(Document.id)
            .where(Document.deleted_at.is_not(None), Document.deleted_at <= cutoff)
            .order_by(Document.deleted_at, Document.id)
            .limit(MAX_CLEANUP_DOCUMENTS)
        )
    )


def cleanup_document(db: Session, document_id: UUID) -> bool:
    """Queue object deletion and remove indexed rows in one database commit."""
    document = db.get(Document, document_id)
    if document is None or document.deleted_at is None:
        return False
    enqueue_document_storage(db, user_id=document.user_id, document_id=document_id)
    versions = list(
        db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == document_id))
    )
    version_ids = [version.id for version in versions]
    if version_ids:
        db.execute(delete(DocumentChunk).where(DocumentChunk.document_version_id.in_(version_ids)))
        db.execute(delete(DocumentVersion).where(DocumentVersion.id.in_(version_ids)))
    db.execute(delete(IngestionJob).where(IngestionJob.document_id == document_id))
    db.execute(delete(Document).where(Document.id == document_id, Document.deleted_at.is_not(None)))
    db.commit()
    return True


def drain_storage_deletions(db: Session, storage: DeletingStorage) -> int:
    keys = list(
        db.scalars(
            select(StorageDeletion.object_key)
            .order_by(StorageDeletion.created_at, StorageDeletion.object_key)
            .limit(100)
        )
    )
    failed = 0
    for key in keys:
        try:
            storage.delete(key)
        except StorageError:
            failed += 1
            continue
        db.execute(delete(StorageDeletion).where(StorageDeletion.object_key == key))
        db.commit()
    return failed


def main() -> int:
    settings = get_settings()
    if (
        not settings.database_url.startswith("postgresql")
        or not settings.rag_storage_url
        or not settings.rag_storage_service_key
    ):
        return 2
    with SessionLocal() as db:
        ids = deleted_document_ids(db)
    for document_id in ids:
        with SessionLocal() as db:
            cleanup_document(db, document_id)
    with (
        PrivateStorage(
            settings.rag_storage_url, settings.rag_storage_service_key, settings.rag_storage_bucket
        ) as storage,
        SessionLocal() as db,
    ):
        failed = drain_storage_deletions(db, storage)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
