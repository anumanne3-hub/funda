"""Transactional ingestion leases. Each call commits one durable transition."""

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.models import Document, IngestionJob

MAX_ATTEMPTS = 3
LEASE_SECONDS = 300


def claim_job(
    db: Session, *, job_id: UUID | None = None, now: datetime | None = None
) -> IngestionJob | None:
    now = now or datetime.now(UTC)
    eligible = or_(
        IngestionJob.status == "queued",
        and_(IngestionJob.status == "running", IngestionJob.lease_expires_at <= now),
    )
    with db.begin():
        db.execute(
            update(IngestionJob)
            .where(
                IngestionJob.status == "running",
                IngestionJob.attempts >= MAX_ATTEMPTS,
                IngestionJob.lease_expires_at <= now,
            )
            .values(
                status="failed",
                lease_token=None,
                lease_expires_at=None,
                error_code="LEASE_EXPIRED",
                updated_at=now,
            )
        )
        query = (
            select(IngestionJob)
            .join(Document, Document.id == IngestionJob.document_id)
            .where(
                eligible,
                IngestionJob.attempts < MAX_ATTEMPTS,
                Document.deleted_at.is_(None),
                Document.user_id == IngestionJob.user_id,
            )
            .order_by(IngestionJob.created_at, IngestionJob.id)
            .limit(1)
        )
        if job_id is not None:
            query = query.where(IngestionJob.id == job_id)
        job = db.scalar(query.with_for_update(skip_locked=True))
        if job is None:
            return None
        job.status = "running"
        job.attempts += 1
        job.lease_token = uuid4()
        job.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
        job.error_code = None
        job.updated_at = now
        db.flush()
        db.refresh(job)
        return job


def renew_lease(
    db: Session, job_id: UUID, lease_token: UUID, *, now: datetime | None = None
) -> bool:
    now = now or datetime.now(UTC)
    with db.begin():
        result = cast(
            CursorResult,
            db.execute(
                update(IngestionJob)
                .where(
                    IngestionJob.id == job_id,
                    IngestionJob.status == "running",
                    IngestionJob.lease_token == lease_token,
                    IngestionJob.lease_expires_at > now,
                )
                .values(lease_expires_at=now + timedelta(seconds=LEASE_SECONDS), updated_at=now)
            ),
        )
        return result.rowcount == 1


def finish_job(
    db: Session,
    job_id: UUID,
    lease_token: UUID,
    *,
    error_code: str | None = None,
    retryable: bool = False,
    now: datetime | None = None,
) -> bool:
    now = now or datetime.now(UTC)
    if error_code is not None and (not error_code or len(error_code) > 100):
        raise ValueError("error_code must contain 1 to 100 characters")
    with db.begin():
        job = db.scalar(
            select(IngestionJob)
            .where(
                IngestionJob.id == job_id,
                IngestionJob.status == "running",
                IngestionJob.lease_token == lease_token,
                IngestionJob.lease_expires_at > now,
            )
            .with_for_update()
        )
        if job is None:
            return False
        job.status = (
            "queued"
            if error_code and retryable and job.attempts < MAX_ATTEMPTS
            else "failed"
            if error_code
            else "completed"
        )
        job.error_code = error_code
        job.lease_token = None
        job.lease_expires_at = None
        job.updated_at = now
        return True
