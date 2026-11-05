"""One-job orchestration shared by a future GitHub runner and local tests."""

import asyncio
import logging
from collections.abc import Callable
from typing import Protocol
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import IngestionJob
from app.rag.embeddings import EmbeddingError
from app.rag.jobs import LEASE_SECONDS, claim_job, finish_job
from app.rag.storage import StorageError

logger = logging.getLogger(__name__)


class JobProcessor(Protocol):
    async def __call__(self, job: IngestionJob) -> None: ...


class ProcessingError(Exception):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        if not code or len(code) > 100:
            raise ValueError("Processing error code must contain 1 to 100 characters")
        self.code = code
        self.retryable = retryable
        super().__init__(code)


async def run_job(
    job_id: UUID, session_factory: Callable[[], Session], processor: JobProcessor
) -> bool:
    """Claim one requested job and persist its outcome; return False if already claimed."""
    with session_factory() as db:
        job = claim_job(db, job_id=job_id)
    if job is None or job.lease_token is None:
        return False
    lease_token = job.lease_token
    error_code: str | None = None
    retryable = False
    try:
        await asyncio.wait_for(processor(job), timeout=LEASE_SECONDS - 60)
    except TimeoutError:
        error_code = "PROCESSING_TIMEOUT"
        retryable = True
    except ProcessingError as exc:
        error_code = exc.code
        retryable = exc.retryable
    except EmbeddingError:
        error_code = "EMBEDDING_FAILED"
        retryable = True
        logger.error("RAG embedding request failed", extra={"event": "rag.worker.embedding_failed"})
    except StorageError:
        error_code = "STORAGE_FAILED"
        retryable = True
        logger.error("RAG storage request failed", extra={"event": "rag.worker.storage_failed"})
    except SQLAlchemyError:
        error_code = "DATABASE_FAILED"
        retryable = True
        logger.error("RAG database operation failed", extra={"event": "rag.worker.database_failed"})
    except Exception:
        error_code = "PROCESSING_FAILED"
        retryable = True
        logger.error("RAG job processor failed", extra={"event": "rag.worker.failed"})
    with session_factory() as db:
        return finish_job(db, job_id, lease_token, error_code=error_code, retryable=retryable)
