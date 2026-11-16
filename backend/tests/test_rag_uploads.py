from io import BytesIO
from uuid import UUID, uuid4

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.api import documents
from app.main import app
from app.models import DocumentChunk, DocumentVersion, IngestionJob
from app.rag import ingest
from app.rag.contracts import ExtractedText, SourceLocation
from app.rag.ingest import TextIngestionProcessor
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

    def close(self):
        pass


def pdf_upload() -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 20 250 Td (Earth has one moon.) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_text_upload_is_private_idempotent_and_queued(client, monkeypatch):
    storage = FakeStorage()
    monkeypatch.setattr(documents, "upload_storage", lambda: storage)
    monkeypatch.setattr(documents, "dispatch_job", lambda *_args: False)
    client.post(
        "/api/v1/auth/register",
        json={"email": "upload@example.com", "password": "a-long-test-password"},
    ).raise_for_status()
    headers = {"X-CSRF-Token": client.get("/api/v1/auth/csrf").json()["csrf_token"]}
    conversation_id = client.post("/api/v1/conversations", json={}, headers=headers).json()["id"]
    upload_headers = {
        **headers,
        "Idempotency-Key": str(uuid4()),
        "X-Filename": "notes.txt",
        "Content-Type": "text/plain",
    }
    path = f"/api/v1/conversations/{conversation_id}/uploads"
    assert client.post(path, content=b"notes", headers=headers).status_code == 422
    assert (
        client.post(
            path, content=b"%PDF", headers={**upload_headers, "Content-Type": "application/pdf"}
        ).status_code
        == 422
    )
    blank = PdfWriter()
    blank.add_blank_page(width=300, height=300)
    blank_output = BytesIO()
    blank.write(blank_output)
    assert (
        client.post(
            path,
            content=blank_output.getvalue(),
            headers={**upload_headers, "Content-Type": "application/pdf"},
        ).status_code
        == 422
    )
    assert client.post(path, content=b"\xff", headers=upload_headers).status_code == 422
    assert client.post(path, content=b"", headers=upload_headers).status_code == 422
    assert (
        client.post(path, content=b"x" * (2 * 1024 * 1024 + 1), headers=upload_headers).status_code
        == 413
    )
    assert storage.objects == {}
    first = client.post(path, content=b"notes", headers=upload_headers)
    assert first.status_code == 202, first.text
    assert first.json()["status"] == "queued"
    uploads = client.get(path)
    assert uploads.status_code == 200
    assert len(uploads.json()) == 1
    assert uploads.json()[0]["title"] == "notes.txt"
    jobs = client.get(f"/api/v1/conversations/{conversation_id}/ingestion-jobs")
    assert [row["id"] for row in jobs.json()] == [first.json()["id"]]
    assert (
        client.post(path, content=b"notes", headers=upload_headers).json()["id"]
        == first.json()["id"]
    )
    assert client.post(path, content=b"different", headers=upload_headers).status_code == 409
    assert len(storage.objects) == 1
    assert next(iter(storage.objects.values())) == (b"notes", "text/plain")
    with app.state.session_factory() as db:
        version = db.query(DocumentVersion).one()
        assert version.storage_key in storage.objects
        assert version.status == "indexing"

    client.post("/api/v1/auth/logout", headers=headers).raise_for_status()
    client.post(
        "/api/v1/auth/register",
        json={"email": "other-upload@example.com", "password": "a-long-test-password"},
    ).raise_for_status()
    other_headers = {"X-CSRF-Token": client.get("/api/v1/auth/csrf").json()["csrf_token"]}
    assert (
        client.post(path, content=b"notes", headers={**upload_headers, **other_headers}).status_code
        == 404
    )
    assert client.get(f"/api/v1/ingestion-jobs/{first.json()['id']}").status_code == 404
    assert client.get(path).status_code == 404
    assert client.get(f"/api/v1/conversations/{conversation_id}/ingestion-jobs").status_code == 404


@pytest.mark.parametrize(
    ("filename", "media_type", "content", "expected_text"),
    [
        ("notes.txt", "text/plain", b"Earth has one moon.", "Earth has one moon."),
        (
            "notes.md",
            "text/markdown",
            b"# Earth\nEarth has one moon.",
            "# Earth\nEarth has one moon.",
        ),
        (
            "notes.html",
            "text/html",
            b"<h1>Earth</h1><p>Earth has one moon.</p><script>ignore me</script>",
            "Earth has one moon.",
        ),
        ("notes.pdf", "application/pdf", pdf_upload(), "Earth has one moon."),
    ],
)
@pytest.mark.asyncio
async def test_uploaded_file_is_indexed_and_visible_after_worker(
    client, monkeypatch, filename, media_type, content, expected_text
):
    class FakeEmbeddings:
        model = "test-upload"
        dimensions = 2

        async def embed_documents(self, texts):
            return [[float(len(text)), 1.0] for text in texts]

    storage = FakeStorage()
    monkeypatch.setattr(documents, "upload_storage", lambda: storage)
    monkeypatch.setattr(documents, "dispatch_job", lambda *_args: True)
    client.post(
        "/api/v1/auth/register",
        json={"email": f"{uuid4()}@example.com", "password": "a-long-test-password"},
    ).raise_for_status()
    headers = {"X-CSRF-Token": client.get("/api/v1/auth/csrf").json()["csrf_token"]}
    conversation_id = client.post("/api/v1/conversations", json={}, headers=headers).json()["id"]
    response = client.post(
        f"/api/v1/conversations/{conversation_id}/uploads",
        content=content,
        headers={
            **headers,
            "Idempotency-Key": str(uuid4()),
            "X-Filename": filename,
            "Content-Type": media_type,
        },
    )
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]
    processor = TextIngestionProcessor(
        app.state.session_factory,
        storage,
        FakeEmbeddings(),
        allowed_urls=set(),
        vector_writer=lambda *_args: None,
    )
    assert await run_job(UUID(job_id), app.state.session_factory, processor)
    assert client.get(f"/api/v1/ingestion-jobs/{job_id}").json()["status"] == "completed"
    assert [
        row["title"]
        for row in client.get(f"/api/v1/conversations/{conversation_id}/uploads").json()
    ] == [filename]
    with app.state.session_factory() as db:
        assert db.get(IngestionJob, UUID(job_id)).status == "completed"
        assert db.query(DocumentVersion).one().status == "ready"
        chunks = db.query(DocumentChunk).all()
        assert chunks and expected_text in " ".join(chunk.content for chunk in chunks)
        assert "ignore me" not in " ".join(chunk.content for chunk in chunks)
        if media_type == "application/pdf":
            assert all(chunk.page == 1 for chunk in chunks)


@pytest.mark.asyncio
async def test_image_upload_is_gated_then_indexed_with_location(client, monkeypatch):
    class FakeEmbeddings:
        model = "test-image"
        dimensions = 2

        async def embed_documents(self, texts):
            return [[1.0, 2.0] for _ in texts]

    image = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR"
        + (100).to_bytes(4, "big") * 2
        + b"\x08\x02\x00\x00\x00\x00\x00\x00\x00"
    )
    storage = FakeStorage()
    monkeypatch.setattr(documents, "upload_storage", lambda: storage)
    monkeypatch.setattr(documents, "dispatch_job", lambda *_args: True)
    client.post(
        "/api/v1/auth/register",
        json={"email": f"{uuid4()}@example.com", "password": "a-long-test-password"},
    ).raise_for_status()
    headers = {"X-CSRF-Token": client.get("/api/v1/auth/csrf").json()["csrf_token"]}
    conversation_id = client.post("/api/v1/conversations", json={}, headers=headers).json()["id"]
    path = f"/api/v1/conversations/{conversation_id}/uploads"
    upload_headers = {
        **headers,
        "Idempotency-Key": str(uuid4()),
        "X-Filename": "earth.png",
        "Content-Type": "image/png",
    }
    assert client.post(path, content=image, headers=upload_headers).status_code == 415
    settings = documents.get_settings().model_copy(update={"rag_image_upload_enabled": True})
    monkeypatch.setattr(documents, "get_settings", lambda: settings)
    assert client.get("/api/v1/rag/capabilities").json() == {"image_upload_enabled": True}
    assert client.post(path, content=b"not an image", headers=upload_headers).status_code == 422
    response = client.post(path, content=image, headers=upload_headers)
    assert response.status_code == 202, response.text
    monkeypatch.setattr(
        ingest,
        "extract_image_text",
        lambda *_args: [ExtractedText("Earth has one moon.", SourceLocation(section="Image"))],
    )
    processor = TextIngestionProcessor(
        app.state.session_factory,
        storage,
        FakeEmbeddings(),
        allowed_urls=set(),
        vector_writer=lambda *_args: None,
    )
    job_id = UUID(response.json()["id"])
    assert await run_job(job_id, app.state.session_factory, processor)
    with app.state.session_factory() as db:
        assert db.get(IngestionJob, job_id).status == "completed"
        chunk = db.query(DocumentChunk).one()
        assert chunk.content == "Earth has one moon."
        assert chunk.section == "Image"
