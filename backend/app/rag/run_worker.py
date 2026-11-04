"""GitHub Actions entry point for a single durable ingestion job."""

import asyncio
import sys
from uuid import UUID

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import IngestionJob
from app.rag.embeddings import NvidiaEmbeddings
from app.rag.ingest import TextIngestionProcessor
from app.rag.storage import PrivateStorage
from app.rag.worker import run_job


async def run(job_id: UUID) -> int:
    settings = get_settings()
    if (
        not settings.database_url.startswith("postgresql")
        or not settings.rag_storage_url
        or not settings.rag_storage_service_key
        or not settings.rag_embedding_api_key
    ):
        return 2  # Leave the job queued; deployment inputs are incomplete.
    storage = PrivateStorage(
        settings.rag_storage_url, settings.rag_storage_service_key, settings.rag_storage_bucket
    )
    embeddings = NvidiaEmbeddings(
        settings.rag_embedding_api_key,
        model=settings.rag_embedding_model,
        dimensions=settings.rag_embedding_dimensions,
    )
    try:
        processor = TextIngestionProcessor(
            SessionLocal,
            storage,
            embeddings,
            allowed_urls=set(settings.rag_allowed_source_urls),
        )
        claimed = await run_job(job_id, SessionLocal, processor)
        if not claimed:
            return 0  # Duplicate workflow delivery or a job already settled.
        with SessionLocal() as db:
            job = db.get(IngestionJob, job_id)
            return 0 if job is not None and job.status == "completed" else 1
    finally:
        storage.close()
        await embeddings.close()


def main() -> int:
    if len(sys.argv) != 2:
        return 2
    try:
        job_id = UUID(sys.argv[1])
    except ValueError:
        return 2
    return asyncio.run(run(job_id))


if __name__ == "__main__":
    raise SystemExit(main())
