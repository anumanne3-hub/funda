-- Initial chat schema. Apply only to an empty application schema.
CREATE TABLE anonymous_sessions (
    id UUID NOT NULL, 
    token_hash VARCHAR(64) NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (token_hash)
);

CREATE TABLE conversations (
    id UUID NOT NULL, 
    anonymous_session_id UUID NOT NULL, 
    title VARCHAR(200) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(anonymous_session_id) REFERENCES anonymous_sessions (id) ON DELETE CASCADE
);

CREATE INDEX ix_conversations_owner_updated ON conversations (anonymous_session_id, updated_at);

CREATE TABLE messages (
    id UUID NOT NULL, 
    conversation_id UUID NOT NULL, 
    sequence_number INTEGER NOT NULL, 
    role VARCHAR(20) NOT NULL, 
    content TEXT NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    provider_request_id VARCHAR(200), 
    error_code VARCHAR(100), 
    input_tokens INTEGER, 
    output_tokens INTEGER, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_messages_role CHECK (role IN ('user','assistant','system')), 
    CONSTRAINT ck_messages_status CHECK (status IN ('pending','completed','failed')), 
    CONSTRAINT uq_message_sequence UNIQUE (conversation_id, sequence_number), 
    FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
);

CREATE INDEX ix_messages_conversation_created ON messages (conversation_id, created_at);

CREATE TABLE chat_requests (
    id UUID NOT NULL, 
    conversation_id UUID NOT NULL, 
    user_message_id UUID NOT NULL, 
    assistant_message_id UUID NOT NULL, 
    idempotency_key VARCHAR(100) NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    model VARCHAR(200) NOT NULL, 
    prompt_version VARCHAR(50) NOT NULL, 
    duration_ms INTEGER, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_requests_status CHECK (status IN ('pending','completed','failed')), 
    CONSTRAINT uq_request_idempotency UNIQUE (conversation_id, idempotency_key), 
    FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE, 
    FOREIGN KEY(user_message_id) REFERENCES messages (id), 
    FOREIGN KEY(assistant_message_id) REFERENCES messages (id)
);
