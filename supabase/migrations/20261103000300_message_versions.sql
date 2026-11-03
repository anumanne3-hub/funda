CREATE TABLE message_versions (
    id UUID PRIMARY KEY,
    message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    parent_version_id UUID REFERENCES message_versions(id) ON DELETE SET NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT uq_message_version UNIQUE (message_id, version_number)
);

CREATE TABLE message_feedback (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    version_id UUID NOT NULL REFERENCES message_versions(id) ON DELETE CASCADE,
    rating INTEGER NOT NULL,
    note TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT ck_feedback_rating CHECK (rating IN (-1,1)),
    CONSTRAINT uq_feedback_user_version UNIQUE (user_id, version_id)
);

INSERT INTO message_versions (id, message_id, version_number, content, created_at)
SELECT gen_random_uuid(), id, 1, content, created_at FROM messages;

ALTER TABLE message_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE message_feedback ENABLE ROW LEVEL SECURITY;
