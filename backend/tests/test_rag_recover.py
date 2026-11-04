from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.main import app
from app.models import Document, IngestionJob
from app.rag import recover


def test_recovery_selects_queued_and_expired_owned_jobs(client):
    client.post(
        "/api/v1/auth/register",
        json={"email": "recover@example.com", "password": "a-long-test-password"},
    ).raise_for_status()
    now = datetime.now(UTC)
    with app.state.session_factory() as db:
        from app.models import User

        user = db.query(User).one()
        from app.models import Conversation

        conversation = Conversation(user_id=user.id, title="Recovery")
        db.add(conversation)
        db.flush()
        documents = [
            Document(
                user_id=user.id,
                conversation_id=conversation.id,
                source_kind="upload",
                source_key=str(uuid4()),
                title=f"File {index}",
            )
            for index in range(5)
        ]
        db.add_all(documents)
        db.flush()
        jobs = [
            IngestionJob(
                user_id=user.id,
                document_id=document.id,
                idempotency_key=str(uuid4()),
                status=status,
                attempts=attempts,
                lease_token=uuid4() if status == "running" else None,
                lease_expires_at=expires,
            )
            for document, (status, attempts, expires) in zip(
                documents,
                [
                    ("queued", 0, None),
                    ("running", 1, now - timedelta(seconds=1)),
                    ("running", 1, now + timedelta(minutes=5)),
                    ("completed", 1, None),
                    ("queued", 3, None),
                ],
                strict=True,
            )
        ]
        db.add_all(jobs)
        db.commit()
        expected = {jobs[0].id, jobs[1].id}
        assert set(recover.recovery_job_ids(db, now=now)) == expected
        documents[0].deleted_at = now
        db.commit()
        assert recover.recovery_job_ids(db, now=now) == [jobs[1].id]


@pytest.mark.asyncio
async def test_reconciliation_continues_after_a_failed_job(monkeypatch):
    ids = [uuid4(), uuid4()]
    monkeypatch.setattr(recover, "recovery_job_ids", lambda _db: ids)

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(recover, "SessionLocal", lambda: FakeSession())
    seen: list[UUID] = []

    async def fake_run(job_id: UUID) -> int:
        seen.append(job_id)
        return 1 if job_id == ids[0] else 0

    monkeypatch.setattr(recover, "run", fake_run)
    assert await recover.reconcile() == 1
    assert seen == ids
