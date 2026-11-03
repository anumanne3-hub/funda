CREATE TABLE users (
    id UUID PRIMARY KEY,
    email VARCHAR(320) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE account_sessions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    csrf_hash VARCHAR(64) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    revoked_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);
CREATE INDEX ix_account_sessions_user ON account_sessions (user_id);

CREATE TABLE projects (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);
CREATE INDEX ix_projects_user ON projects (user_id);

ALTER TABLE conversations ALTER COLUMN anonymous_session_id DROP NOT NULL;
ALTER TABLE conversations ADD COLUMN user_id UUID REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE conversations ADD COLUMN project_id UUID REFERENCES projects(id) ON DELETE SET NULL;
ALTER TABLE conversations ADD CONSTRAINT ck_conversation_owner CHECK ((anonymous_session_id IS NULL) <> (user_id IS NULL));
CREATE INDEX ix_conversations_user_updated ON conversations (user_id, updated_at);

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE account_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
