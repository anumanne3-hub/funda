CREATE TABLE storage_deletions (
    object_key VARCHAR(500) PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);
ALTER TABLE storage_deletions ENABLE ROW LEVEL SECURITY;
