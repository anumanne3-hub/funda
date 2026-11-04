from uuid import uuid4

from app.api import documents
from app.main import app
from app.models import DocumentVersion


class FakeStorage:
    def __init__(self):
        self.objects = {}

    def put(self, key, content, media_type):
        self.objects[key] = (content, media_type)

    def delete(self, key):
        self.objects.pop(key, None)

    def close(self):
        pass


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
        == 415
    )
    assert client.post(path, content=b"\xff", headers=upload_headers).status_code == 422
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
