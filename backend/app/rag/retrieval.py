"""Owner and scope filtered vector retrieval over published document versions."""

import json
import math
from collections.abc import Callable

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Conversation, Project
from app.rag.contracts import EmbeddingProvider, RetrievalScope, RetrievedEvidence, SourceLocation


class ScopeAccessError(Exception):
    pass


class VectorRetrieval:
    def __init__(
        self, session_factory: Callable[[], Session], embeddings: EmbeddingProvider
    ) -> None:
        self.session_factory = session_factory
        self.embeddings = embeddings

    async def search(
        self, scope: RetrievalScope, query: str, *, limit: int = 5
    ) -> list[RetrievedEvidence]:
        if not query.strip() or len(query) > 2000 or not 1 <= limit <= 20:
            raise ValueError("Invalid retrieval query or limit")
        with self.session_factory() as db:
            self._authorize(db, scope)
        vector = await self.embeddings.embed_query(query)
        if len(vector) != 2048 or not all(math.isfinite(value) for value in vector):
            raise ValueError("Query embedding has incompatible shape")
        filters: list[str] = []
        params: dict[str, object] = {
            "user_id": scope.user_id,
            "model": self.embeddings.model,
            "dimensions": self.embeddings.dimensions,
            "embedding": json.dumps(vector, separators=(",", ":")),
            "limit": limit,
        }
        if scope.project_id is not None:
            filters.append("d.project_id = :project_id")
            params["project_id"] = scope.project_id
        if scope.conversation_id is not None:
            filters.append("d.conversation_id = :conversation_id")
            params["conversation_id"] = scope.conversation_id
        scope_filter = " OR ".join(filters)
        authorization_filters: list[str] = []
        if scope.project_id is not None:
            authorization_filters.append(
                "EXISTS (SELECT 1 FROM projects p "
                "WHERE p.id = :project_id AND p.user_id = :user_id)"
            )
        if scope.conversation_id is not None:
            relation = "AND co.project_id = :project_id " if scope.project_id is not None else ""
            authorization_filters.append(
                "EXISTS (SELECT 1 FROM conversations co "
                "WHERE co.id = :conversation_id AND co.user_id = :user_id "
                f"{relation})"
            )
        authorization_filter = " AND ".join(authorization_filters)
        statement = text(
            "WITH latest AS ("
            " SELECT id, document_id, embedding_model, embedding_dimensions,"
            " ROW_NUMBER() OVER (PARTITION BY document_id ORDER BY published_at DESC, id DESC) rn"
            " FROM document_versions WHERE status = 'ready'"
            ") "
            "SELECT d.id AS document_id, v.id AS document_version_id, c.id AS chunk_id,"
            " d.title, d.source_kind, d.source_key, c.content, c.page, c.section,"
            " c.start_ms, c.end_ms "
            "FROM documents d JOIN latest v ON v.document_id = d.id AND v.rn = 1 "
            "JOIN document_chunks c ON c.document_version_id = v.id "
            f"WHERE d.user_id = :user_id AND d.deleted_at IS NULL AND ({scope_filter}) "
            f"AND ({authorization_filter}) "
            "AND v.embedding_model = :model AND v.embedding_dimensions = :dimensions "
            "AND c.embedding IS NOT NULL "
            "ORDER BY c.embedding OPERATOR(extensions.<=>) "
            "CAST(:embedding AS extensions.vector(2048)) ASC LIMIT :limit"
        )
        with self.session_factory() as db:
            rows = db.execute(statement, params).mappings().all()
        return [
            RetrievedEvidence(
                document_id=row["document_id"],
                document_version_id=row["document_version_id"],
                chunk_id=row["chunk_id"],
                title=row["title"],
                text=row["content"],
                location=SourceLocation(
                    page=row["page"],
                    section=row["section"],
                    start_ms=row["start_ms"],
                    end_ms=row["end_ms"],
                ),
                source_url=row["source_key"] if row["source_kind"] == "website" else None,
            )
            for row in rows
        ]

    @staticmethod
    def _authorize(db: Session, scope: RetrievalScope) -> None:
        if scope.project_id is not None:
            project = db.scalar(
                select(Project.id).where(
                    Project.id == scope.project_id, Project.user_id == scope.user_id
                )
            )
            if project is None:
                raise ScopeAccessError("Project not found")
        if scope.conversation_id is not None:
            conversation = db.scalar(
                select(Conversation).where(
                    Conversation.id == scope.conversation_id,
                    Conversation.user_id == scope.user_id,
                )
            )
            if conversation is None or (
                scope.project_id is not None and conversation.project_id != scope.project_id
            ):
                raise ScopeAccessError("Conversation not found in scope")
