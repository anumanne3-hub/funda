import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base


class MessageCitation(Base):
    __tablename__ = "message_citations"
    __table_args__ = (
        UniqueConstraint("message_version_id", "ordinal", name="uq_message_citation_ordinal"),
        CheckConstraint("ordinal >= 1", name="ck_citation_ordinal"),
        CheckConstraint("page IS NULL OR page > 0", name="ck_citation_page"),
        CheckConstraint("start_ms IS NULL OR start_ms >= 0", name="ck_citation_start"),
        CheckConstraint(
            "end_ms IS NULL OR end_ms >= coalesce(start_ms, 0)", name="ck_citation_end"
        ),
        Index("ix_message_citations_version", "message_version_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    message_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("message_versions.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    document_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    chunk_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500))
    page: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(500))
    start_ms: Mapped[int | None] = mapped_column(Integer)
    end_ms: Mapped[int | None] = mapped_column(Integer)
