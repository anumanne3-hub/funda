-- RAG metadata is private to the API and worker; browser roles receive no policies.
CREATE TABLE documents (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    source_kind VARCHAR(20) NOT NULL,
    source_key VARCHAR(500) NOT NULL,
    title VARCHAR(500) NOT NULL,
    storage_key VARCHAR(500),
    deleted_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT ck_document_scope CHECK ((project_id IS NULL) <> (conversation_id IS NULL)),
    CONSTRAINT ck_document_source_kind CHECK (source_kind IN ('upload','website','cloud')),
    CONSTRAINT uq_document_source UNIQUE (user_id, source_kind, source_key)
);
CREATE INDEX ix_documents_project ON documents (user_id, project_id, deleted_at);
CREATE INDEX ix_documents_conversation ON documents (user_id, conversation_id, deleted_at);

CREATE TABLE document_versions (
    id UUID PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content_hash VARCHAR(64) NOT NULL,
    storage_key VARCHAR(500),
    media_type VARCHAR(100),
    status VARCHAR(20) NOT NULL,
    embedding_model VARCHAR(200),
    embedding_dimensions INTEGER,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    published_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT ck_document_version_status CHECK (status IN ('indexing','ready','failed')),
    CONSTRAINT ck_embedding_dimensions CHECK (embedding_dimensions IS NULL OR embedding_dimensions > 0),
    CONSTRAINT ck_document_version_published CHECK ((status = 'ready') = (published_at IS NOT NULL)),
    CONSTRAINT uq_document_content UNIQUE (document_id, content_hash)
);
CREATE INDEX ix_document_versions_ready ON document_versions (document_id, status);

CREATE TABLE document_chunks (
    id UUID PRIMARY KEY,
    document_version_id UUID NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    content TEXT NOT NULL,
    page INTEGER,
    section VARCHAR(500),
    start_ms INTEGER,
    end_ms INTEGER,
    start_offset INTEGER NOT NULL,
    end_offset INTEGER NOT NULL,
    CONSTRAINT uq_document_chunk_ordinal UNIQUE (document_version_id, ordinal),
    CONSTRAINT ck_document_chunk_location CHECK (page IS NULL OR page > 0),
    CONSTRAINT ck_document_chunk_time CHECK (start_ms IS NULL OR start_ms >= 0),
    CONSTRAINT ck_document_chunk_end_time CHECK (end_ms IS NULL OR end_ms >= coalesce(start_ms, 0)),
    CONSTRAINT ck_document_chunk_offsets CHECK (start_offset >= 0 AND end_offset > start_offset)
);

CREATE TABLE ingestion_jobs (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    idempotency_key VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    attempts INTEGER NOT NULL DEFAULT 0,
    lease_token UUID,
    lease_expires_at TIMESTAMP WITH TIME ZONE,
    error_code VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT uq_ingestion_job_key UNIQUE (user_id, idempotency_key),
    CONSTRAINT ck_ingestion_job_status CHECK (status IN ('queued','running','completed','failed')),
    CONSTRAINT ck_ingestion_job_attempts CHECK (attempts >= 0),
    CONSTRAINT ck_ingestion_job_lease CHECK ((lease_token IS NULL) = (lease_expires_at IS NULL)),
    CONSTRAINT ck_ingestion_job_running CHECK (status = 'running' OR lease_token IS NULL)
);
CREATE INDEX ix_ingestion_jobs_claim ON ingestion_jobs (status, lease_expires_at, created_at);
CREATE INDEX ix_ingestion_jobs_owner ON ingestion_jobs (user_id, created_at);

ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion_jobs ENABLE ROW LEVEL SECURITY;
