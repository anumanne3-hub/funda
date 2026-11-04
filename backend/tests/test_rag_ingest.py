import hashlib
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.main import app
from app.models import (
    Conversation,
    Document,
    DocumentChunk,
    DocumentVersion,
    IngestionJob,
    Project,
    User,
)
from app.rag.ingest import TextIngestionProcessor
from app.rag.storage import object_key
from app.rag.worker import run_job


class FakeStorage:
    def __init__(self):
        self.objects = {}

    def put(self, key, content, media_type):
        self.objects[key] = (content, media_type)

    def get(self, key):
        return self.objects[key][0]

    def delete(self, key):
        self.objects.pop(key, None)


class FakeEmbeddings:
    model = "fake-v1"
    dimensions = 2

    async def embed_documents(self, texts):
        return [[float(len(text)), 1.0] for text in texts]

    async def embed_query(self, text):
        return [float(len(text)), 1.0]


def seed_website_job():
    factory = app.state.session_factory
    with factory() as db:
        user = User(email=f"{uuid4()}@example.com", password_hash="test")
        db.add(user)
        db.flush()
        project = Project(user_id=user.id, name="P")
        db.add(project)
        db.flush()
        document = Document(
            user_id=user.id,
            project_id=project.id,
            source_kind="website",
            source_key="https://example.com/page",
            title="Page",
        )
        db.add(document)
        db.flush()
        job = IngestionJob(user_id=user.id, document_id=document.id, idempotency_key=str(uuid4()))
        db.add(job)
        db.commit()
        return job.id, document.id


@pytest.mark.asyncio
async def test_website_job_publishes_chunks_once(client):
    job_id, document_id = seed_website_job()
    storage = FakeStorage()
    written = []

    async def fetch(_url, _allowed):
        return "text/html", b"<h1>Facts</h1><p>Earth orbits the Sun.</p>"

    processor = TextIngestionProcessor(
        app.state.session_factory,
        storage,
        FakeEmbeddings(),
        allowed_urls={"https://example.com/page"},
        vector_writer=lambda _db, chunk_id, vector: written.append((chunk_id, vector)),
        fetch=fetch,
    )
    assert await run_job(job_id, app.state.session_factory, processor)
    with app.state.session_factory() as db:
        version = db.scalar(
            select(DocumentVersion).where(DocumentVersion.document_id == document_id)
        )
        assert version is not None and version.status == "ready"
        assert version.embedding_model == "fake-v1" and version.embedding_dimensions == 2
        chunks = list(db.scalars(select(DocumentChunk)))
        assert len(chunks) == 1 and chunks[0].section == "Facts"
        assert chunks[0].content == "Earth orbits the Sun."
        assert written == [(chunks[0].id, [21.0, 1.0])]
        assert version.storage_key in storage.objects
        assert db.get(IngestionJob, job_id).status == "completed"


@pytest.mark.asyncio
async def test_vector_failure_rolls_back_publication_and_cleans_original(client):
    job_id, document_id = seed_website_job()
    storage = FakeStorage()

    async def fetch(_url, _allowed):
        return "text/plain", b"A small document"

    def fail_vector(_db, _chunk_id, _vector):
        raise RuntimeError("vector unavailable")

    processor = TextIngestionProcessor(
        app.state.session_factory,
        storage,
        FakeEmbeddings(),
        allowed_urls={"https://example.com/page"},
        vector_writer=fail_vector,
        fetch=fetch,
    )
    assert await run_job(job_id, app.state.session_factory, processor)
    with app.state.session_factory() as db:
        assert (
            db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == document_id))
            is None
        )
        assert db.scalar(select(DocumentChunk)) is None
        assert db.get(IngestionJob, job_id).status == "queued"
    assert storage.objects == {}


@pytest.mark.asyncio
async def test_upload_job_reads_private_original_and_publishes(client):
    factory = app.state.session_factory
    storage = FakeStorage()
    original = b"Private notes"
    with factory() as db:
        user = User(email=f"{uuid4()}@example.com", password_hash="test")
        db.add(user)
        db.flush()
        conversation = Conversation(user_id=user.id, title="Chat")
        db.add(conversation)
        db.flush()
        document = Document(
            user_id=user.id,
            conversation_id=conversation.id,
            source_kind="upload",
            source_key=str(uuid4()),
            title="notes.txt",
        )
        db.add(document)
        db.flush()
        version_id = uuid4()
        path = object_key(user.id, document.id, version_id)
        version = DocumentVersion(
            id=version_id,
            document_id=document.id,
            content_hash=hashlib.sha256(original).hexdigest(),
            storage_key=path,
            media_type="text/plain",
            status="indexing",
        )
        job = IngestionJob(user_id=user.id, document_id=document.id, idempotency_key=str(uuid4()))
        db.add_all([version, job])
        db.commit()
        job_id = job.id
    storage.put(path, original, "text/plain")
    processor = TextIngestionProcessor(
        factory,
        storage,
        FakeEmbeddings(),
        allowed_urls=set(),
        vector_writer=lambda *_args: None,
    )
    assert await run_job(job_id, factory, processor)
    with factory() as db:
        assert db.get(DocumentVersion, version_id).status == "ready"
        assert db.get(IngestionJob, job_id).status == "completed"
    assert storage.objects[path] == (original, "text/plain")
