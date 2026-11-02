# Milestone 1 architecture and API

React talks to FastAPI through credentialed HTTP and a WebSocket. PostgreSQL is the durable store;
SQLAlchemy sessions are short-lived and released before provider streaming. Alembic owns the schema.
The provider can be mock, native Gemini, or an OpenAI-compatible chat-completion endpoint.

## Identity and privacy

The browser receives a random, opaque HttpOnly session cookie. Only its SHA-256 hash is stored.
Every conversation query and message write uses the server-derived owner ID; bodies cannot choose
an owner. Sessions expire after 30 days by default and are rechecked on every WebSocket message.
Production startup rejects SQLite, insecure cookies and non-HTTPS/wildcard frontend origins.
Mutation and WebSocket origins are checked. Logs contain request/event IDs, not prompts or credentials.
Anonymous identity depends on keeping the cookie; clearing it loses access to existing conversations.
Retention/deletion controls and account claiming are later milestones.

## HTTP contract

| Method/path | Behavior |
| --- | --- |
| GET `/health` | Process liveness |
| GET `/ready` | Database and limit-table availability; 503 when unavailable |
| POST `/api/v1/anonymous-session` | Reuse/create anonymous identity and cookie |
| POST `/api/v1/conversations` | Create an owned conversation (`title`, up to 200 characters) |
| GET `/api/v1/conversations?limit=20&cursor=UUID` | Owned conversations ordered by updated time and UUID |
| GET `/api/v1/conversations/UUID` | Owned conversation with messages in sequence order |

HTTP failures use `code`, `message`, `request_id`; input values and internal exceptions are omitted.
Timestamps use UTC. Pagination applies a composite time/UUID boundary, including tied timestamps.
An HTTP message-submission endpoint is not provided: the versioned WebSocket below submits messages.

## WebSocket `/api/v1/ws/chat`

Server first emits `connection.ready`. Send:

```json
{"type":"chat.send","request_id":"UUID","conversation_id":"UUID","idempotency_key":"unique-key-at-least-8-chars","content":"Hello"}
```

`idempotency_key` is the WebSocket equivalent of an HTTP `Idempotency-Key` header. Reuse it on retry.
Events are `message.started`, `message.delta`, `message.completed`, or `error`. Errors include a
safe code and `retryable` flag. Message size is bounded at both transport and schema layers.

The database locks the owned conversation before checking the key or allocating sequence numbers.
A unique key belongs to one content payload; using it with different content is rejected.
User/assistant/request rows commit together before a provider call. A completed retry replays the
saved result. A pending retry polls without another provider call. A failed retry remains failed;
the user can explicitly submit a new message. Unknown outcomes are never automatically charged again.

Provider generation continues to its bounded timeout after browser disconnect and persists the result.
After process death, a retried pending request older than timeout plus 30 seconds becomes interrupted.
The browser keeps the pending payload/key in sessionStorage until it reconciles the outcome; switching
conversations, reconnecting, or reloading reuses the same key.

## Costs, limits and schema

Tables: `anonymous_sessions`, `conversations`, `messages`, `chat_requests`, `limit_buckets`.
Foreign keys and unique conversation/sequence and conversation/key constraints enforce integrity.
Messages store provider request IDs and input/output usage; requests store timing and micro-USD costs.
Rate limits and daily request counts use atomic shared database counters. IP addresses used for HTTP
limits are hashed; configure the server to trust forwarded addresses only from the hosting proxy.

Paid generation reserves a conservative maximum cost (UTF-8 input bytes plus overhead, and the output
limit) before calling the provider. Reservations are not refunded: missing usage or interrupted calls
cannot quietly reopen the budget. Actual cost is recorded separately using configured model prices.
Prices must be maintained when models change. Free-tier mode records zero monetary cost and enforces
the daily request ceiling; the provider account's billing tier remains the source of truth.

This milestone stores history but sends only the current message to the model. Multi-turn context,
summaries, RAG, account authentication and long-term memory are separate roadmap milestones.
