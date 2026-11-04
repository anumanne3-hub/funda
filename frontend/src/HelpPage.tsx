import { useState } from "react";

type ApiItem = { call: string; action: string; request: string; response: string };
const apiItems: ApiItem[] = [
  { call: "POST /anonymous-session", action: "App starts for a guest", request: "No body; browser cookie identifies an existing session", response: "{ id, expires_at }; sets anonymous session cookie" },
  { call: "POST /auth/register · POST /auth/login", action: "Create account or log in", request: "{ email, password }", response: "{ id, email }; sets account and CSRF cookies" },
  { call: "GET /auth/me · GET /auth/csrf", action: "App checks the signed-in user", request: "Session cookie; no body", response: "{ id, email } and { csrf_token }" },
  { call: "POST /auth/refresh", action: "Refresh account session", request: "Session cookie; no body", response: "{ id, email }; rotates session credentials" },
  { call: "POST /auth/logout · POST /auth/logout-all", action: "User menu logout actions", request: "Session cookie and CSRF token; no body", response: "204, empty body" },
  { call: "DELETE /auth/account", action: "Delete account in user menu", request: "Session cookie and CSRF token; no body", response: "204, empty body" },
  { call: "POST /auth/claim-anonymous · POST /auth/discard-anonymous", action: "Claim or discard guest chats", request: "Account and anonymous cookies; no body", response: "{ claimed: number } or 204" },
  { call: "GET /projects · POST /projects", action: "Load or create projects", request: "GET: no body; POST: { name }", response: "Array of { id, name } or one { id, name }" },
  { call: "PATCH /projects/{id} · DELETE /projects/{id}", action: "Rename or delete selected project", request: "PATCH: { name }; DELETE: no body", response: "{ id, name } or 204" },
  { call: "GET /conversations?limit=20&cursor=&project_id=", action: "Load recent chats, more chats, or project filter", request: "Optional cursor and project_id query values; no body", response: "{ items: Conversation[], next_cursor: UUID | null }" },
  { call: "POST /conversations", action: "New conversation", request: "{ title, project_id: UUID | null }", response: "Conversation with id, title, project_id, timestamps, messages[]" },
  { call: "GET /conversations/{id}", action: "Open a conversation", request: "Conversation id in path; no body", response: "Conversation including ordered messages[]" },
  { call: "PATCH /conversations/{id} · DELETE /conversations/{id}", action: "Rename, assign project, or delete a chat", request: "PATCH: { title? , project_id? }; DELETE: no body", response: "Updated Conversation or 204" },
  { call: "GET /messages/{id}/versions", action: "Show message versions", request: "Message id in path; no body", response: "Array of { id, message_id, version_number, parent_version_id, content }" },
  { call: "PATCH /messages/{id}", action: "Edit a message", request: "{ content }", response: "New message version" },
  { call: "POST /messages/{id}/activate/{version_id}", action: "Switch active version", request: "Message and version ids in path; no body", response: "Activated message version" },
  { call: "POST /messages/{id}/feedback", action: "Rate an assistant version", request: "{ version_id, rating: -1 | 1, note? }", response: "204, empty body" },
  { call: "POST /messages/{id}/regenerate", action: "Regenerate assistant answer", request: "{ idempotency_key: UUID }", response: "New message version" },
  { call: "GET /health · GET /ready", action: "Service health checks", request: "No body", response: "Service status JSON" },
];

const tables = [
  { name: "users", columns: "id, email, password_hash, created_at", purpose: "Account identity, secure password verification, and account creation time." },
  { name: "account_sessions", columns: "id, user_id, token_hash, csrf_hash, expires_at, revoked_at, created_at", purpose: "Recognizes signed-in browsers, prevents CSRF, and supports expiry and revocation." },
  { name: "anonymous_sessions", columns: "id, token_hash, expires_at, created_at", purpose: "Keeps guest conversations private and scoped to one browser session." },
  { name: "projects", columns: "id, user_id, name, created_at", purpose: "Groups an account's conversations under named projects." },
  { name: "conversations", columns: "id, anonymous_session_id, user_id, project_id, title, created_at, updated_at", purpose: "Owns each chat, links it to one guest or user and an optional project, and orders recent chats." },
  { name: "messages", columns: "id, conversation_id, sequence_number, role, content, status, provider_request_id, error_code, input_tokens, output_tokens, created_at", purpose: "Stores chat order and text, delivery state, provider trace, errors, and token usage." },
  { name: "chat_requests", columns: "id, conversation_id, user_message_id, assistant_message_id, idempotency_key, status, model, prompt_version, duration_ms, reserved_cost_microusd, cost_microusd, created_at, updated_at", purpose: "Tracks each model call, links its input and output, prevents duplicate sends, and records latency and cost." },
  { name: "message_versions", columns: "id, message_id, version_number, parent_version_id, content, created_at", purpose: "Preserves edits and regenerated answers so a previous version can be viewed or activated." },
  { name: "message_feedback", columns: "id, user_id, version_id, rating, note, created_at", purpose: "Associates a user's rating and optional note with the exact answer version." },
  { name: "regeneration_requests", columns: "id, assistant_message_id, idempotency_key, input_hash, status, version_id, error_code, reserved_cost_microusd, created_at", purpose: "Deduplicates retries and records regeneration outcome and reserved spend." },
  { name: "limit_buckets", columns: "key, value, expires_at", purpose: "Counts requests within a temporary window for rate and usage limits." },
];

export function HelpPage({ onClose }: { onClose: () => void }) {
  const [section, setSection] = useState<"api" | "db">("api");
  return <div className="help-page">
    <header className="help-header"><strong>Funda Help</strong><button type="button" onClick={onClose}>Back to chat</button></header>
    <div className="help-layout">
      <nav className="help-nav" aria-label="Help topics">
        <button className={section === "api" ? "active" : ""} onClick={() => setSection("api")}>API details</button>
        <button className={section === "db" ? "active" : ""} onClick={() => setSection("db")}>DB details</button>
      </nav>
      <article className="help-content">
        {section === "api" ? <>
          <h1>API details</h1><p>HTTP calls use the <code>/api/v1</code> prefix. The browser sends cookies with requests; signed-in write requests include <code>X-CSRF-Token</code>. UUIDs identify records. A 204 response has no body.</p>
          <div className="help-cards">{apiItems.map(item => <section className="help-card" key={item.call}><h2><code>{item.call}</code></h2><p><b>Triggered by:</b> {item.action}</p><p><b>Request:</b> {item.request}</p><p><b>Response:</b> {item.response}</p></section>)}</div>
          <section className="help-card"><h2>WebSocket /api/v1/ws/chat</h2><p><b>Triggered by:</b> Chat connection and sending a message.</p><p><b>Client event:</b> <code>{'{ type: "chat.send", request_id, conversation_id, idempotency_key, content }'}</code>. The key prevents duplicate sends on retry.</p><p><b>Server events:</b> <code>connection.ready</code>, <code>message.started</code>, <code>message.delta</code>, <code>message.completed</code>, or <code>error</code>. Events may include request_id, conversation_id, message_id, content, code, and retryable.</p></section>
        </> : <>
          <h1>DB details</h1><p>These are the application tables defined in the backend models. IDs link related rows; timestamps support ordering, expiry, and audits. Nullable fields hold optional data.</p>
          <div className="help-cards">{tables.map(table => <section className="help-card" key={table.name}><h2><code>{table.name}</code></h2><p><b>Columns:</b> <code>{table.columns}</code></p><p><b>Why stored:</b> {table.purpose}</p></section>)}</div>
        </>}
      </article>
    </div>
  </div>;
}
