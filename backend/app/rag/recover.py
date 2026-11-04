"""Bounded reconciliation of queued and abandoned ingestion jobs."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Document, IngestionJob
from app.rag.jobs import MAX_ATTEMPTS
from app.rag.run_worker import run

MAX_RECOVERY_JOBS = 20


def recovery_job_ids(db: Session, *, now: datetime | None = None) -> list[UUID]:
    now = now or datetime.now(UTC)
    return list(
        db.scalars(
            select(IngestionJob.id)
            .join(Document, Document.id == IngestionJob.document_id)
            .where(
                IngestionJob.user_id == Document.user_id,
                Document.deleted_at.is_(None),
                or_(
                    and_(
                        IngestionJob.status == "queued",
                        IngestionJob.attempts < MAX_ATTEMPTS,
                    ),
                    and_(
                        IngestionJob.status == "running",
                        IngestionJob.lease_expires_at <= now,
                    ),
                ),
            )
            .order_by(IngestionJob.created_at, IngestionJob.id)
            .limit(MAX_RECOVERY_JOBS)
        )
    )


async def reconcile() -> int:
    with SessionLocal() as db:
        job_ids = recovery_job_ids(db)
    failed = False
    for job_id in job_ids:
        result = await run(job_id)
        if result == 2:
            return 2
        failed = failed or result != 0
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(reconcile()))
