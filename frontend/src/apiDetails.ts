// Entries follow the endpoint order in HelpPage. Each line describes one transmitted value.
export const apiDetails: { request: string[]; response: string[] }[] = [
  {
    request: [
      "Guest cookie, if present: lets the server reuse the same private guest session. No JSON body.",
    ],
    response: [
      "id: server-generated session UUID; identifies the guest session without exposing its cookie token.",
      "expires_at: tells when that session stops being valid.",
      "Set-Cookie: stores the opaque guest token in the browser for later chat calls.",
    ],
  },
  {
    request: [
      "email: entered in the popup; normalized for account creation or login lookup.",
      "password: entered in the popup; registration hashes it, login verifies it. The raw password is not stored.",
    ],
    response: [
      "id: account UUID used to identify the signed-in user.",
      "email: normalized address shown in the user menu.",
      "Set-Cookie: account and CSRF tokens let later requests authenticate and protect writes.",
    ],
  },
  {
    request: [
      "Account cookie: identifies the session; neither GET call sends a JSON body.",
    ],
    response: [
      "/auth/me returns id and email so the UI can show account controls.",
      "/auth/csrf returns csrf_token, which the client sends in X-CSRF-Token on signed-in write calls.",
    ],
  },
  {
    request: [
      "Account cookie identifies the old session; X-CSRF-Token proves the write came from this client. No JSON body.",
    ],
    response: [
      "id and email identify the same account after refresh.",
      "New cookies replace the old session and CSRF credentials.",
    ],
  },
  {
    request: [
      "Account cookie chooses the current session or user; X-CSRF-Token authorizes the change. No JSON body.",
    ],
    response: [
      "204 means success with no JSON. Logout revokes the current session; logout-all revokes every account session and clears browser credentials.",
    ],
  },
  {
    request: [
      "Account cookie identifies which account to delete; X-CSRF-Token protects the destructive request. No JSON body.",
    ],
    response: [
      "204 means the account was deleted; account and CSRF cookies are cleared. Related account data is removed through database relationships.",
    ],
  },
  {
    request: [
      "Account cookie identifies the destination account; guest cookie identifies the source chats; X-CSRF-Token protects the write. No JSON body.",
    ],
    response: [
      "Claim returns claimed: number, the count of conversations transferred to the account.",
      "Discard returns 204 with no JSON and clears the guest cookie after deleting its session and chats.",
    ],
  },
  {
    request: [
      "GET uses the account cookie to select the user's projects; no JSON body.",
      "POST name comes from the New project prompt and becomes the displayed project label; X-CSRF-Token protects creation.",
    ],
    response: [
      "GET returns an array; POST returns one project.",
      "Each project has id (used in filters and assignments) and name (shown in the UI).",
    ],
  },
  {
    request: [
      "Path project_id identifies the project to change; ownership is checked using the account cookie.",
      "PATCH name is the replacement label from the rename prompt. DELETE has no JSON body. Both use X-CSRF-Token.",
    ],
    response: [
      "PATCH returns id and updated name so the UI can refresh its project list.",
      "DELETE returns 204; conversations formerly in the project become unassigned.",
    ],
  },
  {
    request: [
      "limit: maximum page size, currently 20 in the UI; keeps responses bounded.",
      "cursor: optional last conversation UUID from the previous page; fetches the next page.",
      "project_id: optional selected project UUID; limits results to that project.",
      "Session cookie identifies whose chats may be listed. No JSON body.",
    ],
    response: [
      "items: array of conversation summaries for the sidebar.",
      "next_cursor: UUID to request another page, or null when there is no next page.",
      "Each conversation includes id, title, project_id, created_at, updated_at, and messages (usually empty in list results).",
    ],
  },
  {
    request: [
      "title: initial label, currently New conversation; can later be renamed or inferred from the first message.",
      "project_id: selected project UUID or null; places the new chat in a project or leaves it unassigned.",
      "Session cookie establishes the owner; X-CSRF-Token protects the write.",
    ],
    response: [
      "id: new conversation UUID used for later messages and navigation.",
      "title and project_id confirm the saved label and grouping.",
      "created_at and updated_at support ordering; messages starts empty.",
    ],
  },
  {
    request: [
      "Path conversation_id comes from the selected chat; the server checks ownership using the session cookie. No JSON body.",
    ],
    response: [
      "id, title, project_id, created_at, updated_at describe the chat.",
      "messages: ordered array; each message has id, sequence_number, role, content, status, error_code, created_at for rendering chat and failure state.",
    ],
  },
  {
    request: [
      "Path conversation_id chooses the chat; ownership is checked.",
      "PATCH title is the new sidebar label when renaming; project_id is a project UUID or null when assigning or clearing a project. Only changed fields are sent.",
      "DELETE has no JSON body. X-CSRF-Token protects both writes.",
    ],
    response: [
      "PATCH returns the updated conversation fields so the UI reflects the new label or project.",
      "DELETE returns 204, meaning the chat and its dependent records were removed.",
    ],
  },
  {
    request: [
      "Path message_id identifies the message whose revisions are requested; account cookie establishes ownership. No JSON body.",
    ],
    response: [
      "Array of versions: id targets activation/feedback; message_id links back to the message; version_number orders revisions; parent_version_id shows ancestry; content is the saved text.",
    ],
  },
  {
    request: [
      "Path message_id selects a completed user message.",
      "content is the edited text entered by the user; it becomes a new saved version and the active message text. X-CSRF-Token protects the edit.",
    ],
    response: [
      "Version id and version_number identify the new revision; message_id links it to the original; parent_version_id points to the previous revision; content echoes the saved text.",
    ],
  },
  {
    request: [
      "Path message_id selects a completed user message; version_id selects the saved revision to restore. No JSON body; X-CSRF-Token protects the change.",
    ],
    response: [
      "A new version row is returned with its own id and version_number; parent_version_id points to the chosen revision, and content is the restored text.",
    ],
  },
  {
    request: [
      "Path message_id selects the assistant message; version_id identifies the exact answer being rated.",
      "rating is -1 or 1 for negative or positive feedback; note is optional explanation. X-CSRF-Token protects the write.",
    ],
    response: [
      "204 means the feedback was saved or updated; there is no JSON body.",
    ],
  },
  {
    request: [
      "Path message_id selects the assistant answer to regenerate.",
      "idempotency_key is a client-generated UUID; retrying with the same key avoids duplicate model work. X-CSRF-Token protects the write.",
    ],
    response: [
      "New version id identifies the generated answer; message_id links it to the assistant message; version_number orders it; parent_version_id records ancestry; content contains the generated text.",
    ],
  },
  {
    request: [
      "No parameters or body. These endpoints are called by service checks rather than chat UI actions.",
    ],
    response: [
      "/health returns { status: 'ok' } when the process is alive.",
      "/ready returns { status: 'ready', database: 'ok' } after database checks succeed; failures return an error status.",
    ],
  },
];
