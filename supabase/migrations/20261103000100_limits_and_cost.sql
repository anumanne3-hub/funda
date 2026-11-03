-- Durable limits and usage costs.
ALTER TABLE chat_requests ADD COLUMN reserved_cost_microusd INTEGER DEFAULT '0' NOT NULL;

ALTER TABLE chat_requests ADD COLUMN cost_microusd INTEGER;

CREATE TABLE limit_buckets (
    key VARCHAR(200) NOT NULL, 
    value INTEGER NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (key)
);

-- Only the backend database role accesses chat data. No browser Data API policies.
ALTER TABLE public.anonymous_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.limit_buckets ENABLE ROW LEVEL SECURITY;
