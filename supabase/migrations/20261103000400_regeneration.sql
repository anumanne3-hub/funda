CREATE TABLE regeneration_requests (
    id UUID PRIMARY KEY,
    assistant_message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    idempotency_key VARCHAR(100) NOT NULL,
    input_hash VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL,
    version_id UUID REFERENCES message_versions(id) ON DELETE SET NULL,
    error_code VARCHAR(100),
    reserved_cost_microusd INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT ck_regeneration_status CHECK (status IN ('pending','completed','failed')),
    CONSTRAINT uq_regeneration_key UNIQUE (assistant_message_id, idempotency_key)
);

ALTER TABLE regeneration_requests ENABLE ROW LEVEL SECURITY;
