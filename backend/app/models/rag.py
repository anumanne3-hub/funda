import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import Uuid

from app.db.base import Base


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "(project_id IS NULL) <> (conversation_id IS NULL)", name="ck_document_scope"
        ),
        CheckConstraint(
            "source_kind IN ('upload','website','cloud')", name="ck_document_source_kind"
        ),
        Index(
            "uq_active_project_source",
            "user_id",
            "project_id",
            "source_kind",
            "source_key",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND project_id IS NOT NULL"),
            sqlite_where=text("deleted_at IS NULL AND project_id IS NOT NULL"),
        ),
        Index("ix_documents_project", "user_id", "project_id", "deleted_at"),
        Index("ix_documents_conversation", "user_id", "conversation_id", "deleted_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE")
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    source_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    source_key: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(500))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('indexing','ready','failed')", name="ck_document_version_status"
        ),
        CheckConstraint(
            "embedding_dimensions IS NULL OR embedding_dimensions > 0",
            name="ck_embedding_dimensions",
        ),
        CheckConstraint(
            "(status = 'ready') = (published_at IS NOT NULL)", name="ck_document_version_published"
        ),
        UniqueConstraint("document_id", "content_hash", name="uq_document_content"),
        Index("ix_document_versions_ready", "document_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(500))
    media_type: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    embedding_model: Mapped[str | None] = mapped_column(String(200))
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_version_id", "ordinal", name="uq_document_chunk_ordinal"),
        CheckConstraint("page IS NULL OR page > 0", name="ck_document_chunk_location"),
        CheckConstraint("start_ms IS NULL OR start_ms >= 0", name="ck_document_chunk_time"),
        CheckConstraint(
            "end_ms IS NULL OR end_ms >= coalesce(start_ms, 0)", name="ck_document_chunk_end_time"
        ),
        CheckConstraint(
            "start_offset >= 0 AND end_offset > start_offset", name="ck_document_chunk_offsets"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(500))
    start_ms: Mapped[int | None] = mapped_column(Integer)
    end_ms: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_ingestion_job_key"),
        CheckConstraint(
            "status IN ('queued','running','completed','failed')", name="ck_ingestion_job_status"
        ),
        CheckConstraint("attempts >= 0", name="ck_ingestion_job_attempts"),
        CheckConstraint(
            "(lease_token IS NULL) = (lease_expires_at IS NULL)", name="ck_ingestion_job_lease"
        ),
        CheckConstraint(
            "status = 'running' OR lease_token IS NULL", name="ck_ingestion_job_running"
        ),
        Index("ix_ingestion_jobs_claim", "status", "lease_expires_at", "created_at"),
        Index("ix_ingestion_jobs_owner", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_token: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
