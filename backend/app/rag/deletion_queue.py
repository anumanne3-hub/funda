"""Persist private object keys before document rows can cascade away."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, DocumentVersion, StorageDeletion


def enqueue_document_storage(
    db: Session,
    *,
    user_id: UUID,
    project_id: UUID | None = None,
    conversation_id: UUID | None = None,
    document_id: UUID | None = None,
) -> int:
    query = select(Document).where(Document.user_id == user_id)
    if project_id is not None:
        query = query.where(Document.project_id == project_id)
    if conversation_id is not None:
        query = query.where(Document.conversation_id == conversation_id)
    if document_id is not None:
        query = query.where(Document.id == document_id)
    documents = list(db.scalars(query))
    if not documents:
        return 0
    keys = {document.storage_key for document in documents if document.storage_key}
    keys.update(
        db.scalars(
            select(DocumentVersion.storage_key).where(
                DocumentVersion.document_id.in_([document.id for document in documents]),
                DocumentVersion.storage_key.is_not(None),
            )
        )
    )
    added = 0
    for key in keys:
        if key and db.get(StorageDeletion, key) is None:
            db.add(StorageDeletion(object_key=key))
            added += 1
    db.flush()
    return added
