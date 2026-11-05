-- A source URL belongs to a project; soft-deleted sources can be registered again.
ALTER TABLE documents DROP CONSTRAINT uq_document_source;
CREATE UNIQUE INDEX uq_active_project_source
    ON documents (user_id, project_id, source_kind, source_key)
    WHERE deleted_at IS NULL AND project_id IS NOT NULL;
