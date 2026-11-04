import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.models import Conversation, Document, DocumentChunk, DocumentVersion, Project, User
from app.rag.contracts import RetrievalScope
from app.rag.ingest import write_pgvector
from app.rag.retrieval import ScopeAccessError, VectorRetrieval


class FakeEmbeddings:
    model = "test-2048"
    dimensions = 2048

    async def embed_query(self, _text):
        return [1.0] + [0.0] * 2047

    async def embed_documents(self, _texts):
        return []


@pytest.mark.asyncio
async def test_retrieval_rejects_unowned_scope_before_embedding(client):
    retrieval = VectorRetrieval(app.state.session_factory, FakeEmbeddings())
    with pytest.raises(ScopeAccessError):
        await retrieval.search(RetrievalScope(uuid4(), uuid4(), None), "query")
    with pytest.raises(ValueError):
        await retrieval.search(RetrievalScope(uuid4(), uuid4(), None), " ")


@pytest.mark.asyncio
async def test_postgres_retrieval_filters_owner_scope_and_readiness():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("pgvector retrieval requires disposable PostgreSQL TEST_DATABASE_URL")
    if not url.rsplit("/", 1)[-1].startswith("funda_test_"):
        raise RuntimeError("Use a dedicated funda_test_* database")
    migrations = sorted((Path(__file__).resolve().parents[2] / "supabase/migrations").glob("*.sql"))
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                for migration in migrations:
                    connection.connection.driver_connection.execute(
                        migration.read_text(), prepare=False
                    )
                factory = sessionmaker(
                    bind=connection,
                    expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                )
                with factory() as db:
                    owner = User(email=f"{uuid4()}@example.com", password_hash="test")
                    other = User(email=f"{uuid4()}@example.com", password_hash="test")
                    db.add_all([owner, other])
                    db.flush()
                    project = Project(user_id=owner.id, name="Private")
                    other_project = Project(user_id=other.id, name="Other")
                    db.add_all([project, other_project])
                    db.flush()
                    conversation = Conversation(
                        user_id=owner.id, project_id=project.id, title="Chat"
                    )
                    db.add(conversation)
                    db.flush()
                    rows = [
                        Document(
                            user_id=owner.id,
                            project_id=project.id,
                            source_kind="website",
                            source_key="https://example.com/own",
                            title="Own",
                        ),
                        Document(
                            user_id=owner.id,
                            conversation_id=conversation.id,
                            source_kind="upload",
                            source_key=str(uuid4()),
                            title="Upload",
                        ),
                        Document(
                            user_id=other.id,
                            project_id=other_project.id,
                            source_kind="website",
                            source_key="https://example.com/other",
                            title="Other",
                        ),
                        Document(
                            user_id=owner.id,
                            project_id=project.id,
                            source_kind="website",
                            source_key="https://example.com/deleted",
                            title="Deleted",
                            deleted_at=datetime.now(UTC),
                        ),
                        Document(
                            user_id=owner.id,
                            project_id=project.id,
                            source_kind="website",
                            source_key="https://example.com/pending",
                            title="Pending",
                        ),
                    ]
                    db.add_all(rows)
                    db.flush()
                    for document in rows:
                        version = DocumentVersion(
                            document_id=document.id,
                            content_hash=uuid4().hex.ljust(64, "0"),
                            status="indexing" if document.title == "Pending" else "ready",
                            embedding_model="test-2048",
                            embedding_dimensions=2048,
                            published_at=(
                                None if document.title == "Pending" else datetime.now(UTC)
                            ),
                        )
                        db.add(version)
                        db.flush()
                        chunk = DocumentChunk(
                            document_version_id=version.id,
                            ordinal=0,
                            content=document.title,
                            section="Evidence",
                            start_offset=0,
                            end_offset=len(document.title),
                        )
                        db.add(chunk)
                        db.flush()
                        vector = (
                            [1.0, 0.0] + [0.0] * 2046
                            if document.title == "Own"
                            else [0.0, 1.0] + [0.0] * 2046
                        )
                        write_pgvector(db, chunk.id, vector)
                    db.commit()
                    owner_id, project_id, conversation_id, other_id = (
                        owner.id,
                        project.id,
                        conversation.id,
                        other.id,
                    )
                retrieval = VectorRetrieval(factory, FakeEmbeddings())
                both = await retrieval.search(
                    RetrievalScope(owner_id, project_id, conversation_id), "query", limit=5
                )
                assert [item.title for item in both] == ["Own", "Upload"]
                assert all(item.location.section == "Evidence" for item in both)
                project_only = await retrieval.search(
                    RetrievalScope(owner_id, project_id, None), "query", limit=5
                )
                assert [item.title for item in project_only] == ["Own"]
                with pytest.raises(ScopeAccessError):
                    await retrieval.search(
                        RetrievalScope(other_id, project_id, conversation_id), "query", limit=5
                    )
            finally:
                transaction.rollback()
    finally:
        engine.dispose()
