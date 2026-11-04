CREATE TABLE message_citations (
    id UUID PRIMARY KEY,
    message_version_id UUID NOT NULL REFERENCES message_versions(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    document_id UUID NOT NULL,
    document_version_id UUID NOT NULL,
    chunk_id UUID NOT NULL,
    title VARCHAR(500) NOT NULL,
    source_url VARCHAR(500),
    page INTEGER,
    section VARCHAR(500),
    start_ms INTEGER,
    end_ms INTEGER,
    CONSTRAINT uq_message_citation_ordinal UNIQUE (message_version_id, ordinal),
    CONSTRAINT ck_citation_ordinal CHECK (ordinal >= 1),
    CONSTRAINT ck_citation_page CHECK (page IS NULL OR page > 0),
    CONSTRAINT ck_citation_start CHECK (start_ms IS NULL OR start_ms >= 0),
    CONSTRAINT ck_citation_end CHECK (end_ms IS NULL OR end_ms >= coalesce(start_ms, 0))
);
CREATE INDEX ix_message_citations_version ON message_citations (message_version_id);
ALTER TABLE message_citations ENABLE ROW LEVEL SECURITY;
