from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.main import app
from app.models import (
    Conversation,
    Document,
    DocumentChunk,
    DocumentVersion,
    IngestionJob,
    StorageDeletion,
    User,
)
from app.rag.cleanup import cleanup_document, deleted_document_ids, drain_storage_deletions
from app.rag.storage import StorageError


class FakeStorage:
    def __init__(self):
        self.deleted: list[str] = []
        self.fail = True

    def delete(self, key: str) -> None:
        if self.fail:
            raise StorageError("Unavailable")
        self.deleted.append(key)


def test_deleted_document_cleanup_retries_storage_then_removes_derived_data(client):
    client.post(
        "/api/v1/auth/register",
        json={"email": "cleanup@example.com", "password": "a-long-test-password"},
    ).raise_for_status()
    now = datetime.now(UTC)
    key = f"{uuid4()}/{uuid4()}/{uuid4()}"
    with app.state.session_factory() as db:
        user = db.query(User).one()
        conversation = Conversation(user_id=user.id, title="Cleanup")
        db.add(conversation)
        db.flush()
        document = Document(
            user_id=user.id,
            conversation_id=conversation.id,
            source_kind="upload",
            source_key=str(uuid4()),
            title="Old file",
            deleted_at=now - timedelta(hours=2),
        )
        db.add(document)
        db.flush()
        version = DocumentVersion(
            document_id=document.id,
            content_hash="a" * 64,
            storage_key=key,
            media_type="text/plain",
            status="ready",
            published_at=now,
        )
        db.add(version)
        db.flush()
        db.add(
            DocumentChunk(
                document_version_id=version.id,
                ordinal=0,
                content="Source",
                start_offset=0,
                end_offset=6,
            )
        )
        db.add(IngestionJob(user_id=user.id, document_id=document.id, idempotency_key=str(uuid4())))
        db.commit()
        document_id = document.id
        assert deleted_document_ids(db, now=now) == [document_id]
        storage = FakeStorage()
        assert cleanup_document(db, document_id)
        assert db.get(Document, document_id) is None
        assert db.query(DocumentVersion).count() == 0
        assert db.query(DocumentChunk).count() == 0
        assert db.query(IngestionJob).count() == 0
        assert db.get(StorageDeletion, key) is not None
        assert drain_storage_deletions(db, storage) == 1
        assert db.get(StorageDeletion, key) is not None
        storage.fail = False
        assert drain_storage_deletions(db, storage) == 0
        assert storage.deleted == [key]
        assert db.get(StorageDeletion, key) is None


@pytest.mark.parametrize("target", ["conversation", "project", "account"])
def test_cascade_delete_queues_private_objects(client, target):
    client.post(
        "/api/v1/auth/register",
        json={"email": f"{target}-delete@example.com", "password": "a-long-test-password"},
    ).raise_for_status()
    headers = {"X-CSRF-Token": client.get("/api/v1/auth/csrf").json()["csrf_token"]}
    project_id = client.post("/api/v1/projects", json={"name": "Sources"}, headers=headers).json()[
        "id"
    ]
    conversation_id = client.post("/api/v1/conversations", json={}, headers=headers).json()["id"]
    key = f"{uuid4()}/{uuid4()}/{uuid4()}"
    with app.state.session_factory() as db:
        user = db.query(User).one()
        document = Document(
            user_id=user.id,
            project_id=UUID(project_id) if target == "project" else None,
            conversation_id=UUID(conversation_id) if target != "project" else None,
            source_kind="upload" if target != "project" else "website",
            source_key=str(uuid4()),
            title="Source",
        )
        db.add(document)
        db.flush()
        db.add(
            DocumentVersion(
                document_id=document.id,
                content_hash="b" * 64,
                storage_key=key,
                status="indexing",
            )
        )
        db.commit()
    path = {
        "conversation": f"/api/v1/conversations/{conversation_id}",
        "project": f"/api/v1/projects/{project_id}",
        "account": "/api/v1/auth/account",
    }[target]
    response = client.delete(path, headers=headers)
    assert response.status_code == 204, response.text
    with app.state.session_factory() as db:
        assert db.get(StorageDeletion, key) is not None
