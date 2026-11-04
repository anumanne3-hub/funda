import hashlib
from asyncio import to_thread
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import account_identity
from app.db.session import get_db
from app.models import Conversation, Document, DocumentVersion, IngestionJob, Project
from app.rag.dispatch import dispatch_job
from app.rag.extract_text import ExtractionError, extract_text
from app.rag.storage import MAX_OBJECT_BYTES, PrivateStorage, StorageError, object_key

router = APIRouter()


class SourceInput(BaseModel):
    url: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=500)


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID | None
    conversation_id: UUID | None
    source_kind: str
    source_key: str
    title: str
    created_at: datetime


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    document_id: UUID
    status: str
    attempts: int
    error_code: str | None
    created_at: datetime
    updated_at: datetime


def owned_project(db: Session, project_id: UUID, user_id: UUID) -> Project:
    project = db.scalar(select(Project).where(Project.id == project_id, Project.user_id == user_id))
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def owned_document(db: Session, document_id: UUID, user_id: UUID) -> Document:
    document = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == user_id,
            Document.deleted_at.is_(None),
        )
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


def upload_storage() -> PrivateStorage:
    settings = get_settings()
    if not settings.rag_storage_url or not settings.rag_storage_service_key:
        raise HTTPException(status_code=503, detail="Private document storage is not configured")
    return PrivateStorage(
        settings.rag_storage_url, settings.rag_storage_service_key, settings.rag_storage_bucket
    )


@router.post("/conversations/{conversation_id}/uploads", response_model=JobRead, status_code=202)
async def upload_to_conversation(
    conversation_id: UUID, request: Request, db: Session = Depends(get_db)
) -> IngestionJob:
    user = account_identity(request, db, csrf=True)
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user.id
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key or len(key) > 100:
        raise HTTPException(status_code=422, detail="Idempotency-Key is required (max 100 chars)")
    title = request.headers.get("X-Filename", "").strip()
    if not title or len(title) > 500 or any(c in title for c in "/\\\r\n\x00"):
        raise HTTPException(status_code=422, detail="A valid X-Filename is required")
    media_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if media_type not in {"text/plain", "text/markdown", "text/html"}:
        raise HTTPException(status_code=415, detail="Unsupported upload type")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_OBJECT_BYTES:
            raise HTTPException(status_code=413, detail="Upload exceeds size limit")
    if not body:
        raise HTTPException(status_code=422, detail="Upload is empty")
    try:
        extract_text(bytes(body), media_type)
    except ExtractionError:
        raise HTTPException(status_code=422, detail="Upload could not be extracted") from None
    content_hash = hashlib.sha256(body).hexdigest()
    prior = db.scalar(
        select(IngestionJob).where(
            IngestionJob.user_id == user.id, IngestionJob.idempotency_key == key
        )
    )
    if prior is not None:
        prior_document = owned_document(db, prior.document_id, user.id)
        prior_version = db.scalar(
            select(DocumentVersion).where(DocumentVersion.document_id == prior.document_id)
        )
        if (
            prior_document.conversation_id != conversation_id
            or prior_document.source_kind != "upload"
            or prior_version is None
            or prior_version.content_hash != content_hash
        ):
            raise HTTPException(status_code=409, detail="Idempotency key conflict")
        if prior.status == "queued":
            dispatch_job(prior.id, get_settings())
        return prior
    document_id, version_id = uuid4(), uuid4()
    path = object_key(user.id, document_id, version_id)
    document = Document(
        id=document_id,
        user_id=user.id,
        conversation_id=conversation_id,
        source_kind="upload",
        source_key=str(document_id),
        title=title,
    )
    version = DocumentVersion(
        id=version_id,
        document_id=document_id,
        content_hash=content_hash,
        storage_key=path,
        media_type=media_type,
        status="indexing",
    )
    job = IngestionJob(user_id=user.id, document_id=document_id, idempotency_key=key)
    db.add_all([document, version, job])
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Idempotency key conflict") from None
    storage = upload_storage()
    try:
        await to_thread(storage.put, path, bytes(body), media_type)
        try:
            db.commit()
        except Exception:
            db.rollback()
            await to_thread(storage.delete, path)
            raise
    except StorageError:
        db.rollback()
        raise HTTPException(status_code=503, detail="Private document storage failed") from None
    finally:
        storage.close()
    db.refresh(job)
    dispatch_job(job.id, get_settings())
    return job


@router.post("/projects/{project_id}/sources", response_model=DocumentRead, status_code=201)
def create_source(
    project_id: UUID, payload: SourceInput, request: Request, db: Session = Depends(get_db)
) -> Document:
    user = account_identity(request, db, csrf=True)
    owned_project(db, project_id, user.id)
    url = payload.url.strip()
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
        or url not in get_settings().rag_allowed_source_urls
    ):
        raise HTTPException(status_code=422, detail="Source URL is not allowed")
    document = Document(
        user_id=user.id,
        project_id=project_id,
        source_kind="website",
        source_key=url,
        title=payload.title.strip(),
    )
    db.add(document)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Source already exists") from None
    db.refresh(document)
    return document


@router.get("/projects/{project_id}/sources", response_model=list[DocumentRead])
def list_sources(
    project_id: UUID, request: Request, db: Session = Depends(get_db)
) -> list[Document]:
    user = account_identity(request, db)
    owned_project(db, project_id, user.id)
    return list(
        db.scalars(
            select(Document)
            .where(
                Document.user_id == user.id,
                Document.project_id == project_id,
                Document.deleted_at.is_(None),
            )
            .order_by(Document.created_at.desc())
        )
    )


@router.get("/conversations/{conversation_id}/uploads", response_model=list[DocumentRead])
def list_uploads(
    conversation_id: UUID, request: Request, db: Session = Depends(get_db)
) -> list[Document]:
    user = account_identity(request, db)
    conversation = db.scalar(
        select(Conversation.id).where(
            Conversation.id == conversation_id, Conversation.user_id == user.id
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return list(
        db.scalars(
            select(Document)
            .where(
                Document.user_id == user.id,
                Document.conversation_id == conversation_id,
                Document.source_kind == "upload",
                Document.deleted_at.is_(None),
            )
            .order_by(Document.created_at.desc(), Document.id.desc())
            .limit(100)
        )
    )


@router.get("/projects/{project_id}/ingestion-jobs", response_model=list[JobRead])
def list_project_jobs(
    project_id: UUID, request: Request, db: Session = Depends(get_db)
) -> list[IngestionJob]:
    user = account_identity(request, db)
    owned_project(db, project_id, user.id)
    return list(
        db.scalars(
            select(IngestionJob)
            .join(Document, IngestionJob.document_id == Document.id)
            .where(
                IngestionJob.user_id == user.id,
                Document.user_id == user.id,
                Document.project_id == project_id,
                Document.deleted_at.is_(None),
            )
            .order_by(IngestionJob.created_at.desc(), IngestionJob.id.desc())
            .limit(100)
        )
    )


@router.get("/conversations/{conversation_id}/ingestion-jobs", response_model=list[JobRead])
def list_conversation_jobs(
    conversation_id: UUID, request: Request, db: Session = Depends(get_db)
) -> list[IngestionJob]:
    user = account_identity(request, db)
    conversation = db.scalar(
        select(Conversation.id).where(
            Conversation.id == conversation_id, Conversation.user_id == user.id
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return list(
        db.scalars(
            select(IngestionJob)
            .join(Document, IngestionJob.document_id == Document.id)
            .where(
                IngestionJob.user_id == user.id,
                Document.user_id == user.id,
                Document.conversation_id == conversation_id,
                Document.deleted_at.is_(None),
            )
            .order_by(IngestionJob.created_at.desc(), IngestionJob.id.desc())
            .limit(100)
        )
    )


@router.get("/documents/{document_id}", response_model=DocumentRead)
def get_document(document_id: UUID, request: Request, db: Session = Depends(get_db)) -> Document:
    user = account_identity(request, db)
    return owned_document(db, document_id, user.id)


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: UUID, request: Request, db: Session = Depends(get_db)) -> None:
    user = account_identity(request, db, csrf=True)
    document = owned_document(db, document_id, user.id)
    document.deleted_at = datetime.now(UTC)
    db.commit()


@router.post("/documents/{document_id}/sync", response_model=JobRead, status_code=202)
def enqueue_sync(
    document_id: UUID, request: Request, db: Session = Depends(get_db)
) -> IngestionJob:
    user = account_identity(request, db, csrf=True)
    owned_document(db, document_id, user.id)
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key or len(key) > 100:
        raise HTTPException(status_code=422, detail="Idempotency-Key is required (max 100 chars)")
    prior = db.scalar(
        select(IngestionJob).where(
            IngestionJob.user_id == user.id, IngestionJob.idempotency_key == key
        )
    )
    if prior is not None:
        if prior.document_id != document_id:
            raise HTTPException(
                status_code=409, detail="Idempotency key belongs to another document"
            )
        if prior.status == "queued":
            dispatch_job(prior.id, get_settings())
        return prior
    job = IngestionJob(user_id=user.id, document_id=document_id, idempotency_key=key)
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        prior = db.scalar(
            select(IngestionJob).where(
                IngestionJob.user_id == user.id, IngestionJob.idempotency_key == key
            )
        )
        if prior is None or prior.document_id != document_id:
            raise HTTPException(status_code=409, detail="Idempotency key conflict") from None
        if prior.status == "queued":
            dispatch_job(prior.id, get_settings())
        return prior
    db.refresh(job)
    dispatch_job(job.id, get_settings())
    return job


@router.get("/ingestion-jobs/{job_id}", response_model=JobRead)
def get_job(job_id: UUID, request: Request, db: Session = Depends(get_db)) -> IngestionJob:
    user = account_identity(request, db)
    job = db.scalar(
        select(IngestionJob)
        .join(Document, IngestionJob.document_id == Document.id)
        .where(
            IngestionJob.id == job_id,
            IngestionJob.user_id == user.id,
            Document.user_id == user.id,
            Document.deleted_at.is_(None),
        )
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
