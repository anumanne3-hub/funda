import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  activateMessageVersion,
  assignProject,
  authenticate,
  claimAnonymous,
  createConversation,
  createProject,
  currentAccount,
  deleteAccount,
  deleteProject,
  deleteConversation,
  discardAnonymous,
  editMessage,
  ensureSession,
  getConversation,
  listConversations,
  listProjects,
  listMessageVersions,
  logout,
  logoutAll,
  renameConversation,
  renameProject,
  regenerateMessage,
  sendMessageFeedback,
} from "./api/client";
import type {
  Account,
  ApiMessage,
  Conversation,
  MessageVersion,
  Project,
} from "./api/client";
import { websocketUrl } from "./api/chatSocket";
import type { ConnectionState, ServerEvent } from "./api/chatSocket";

type Pending = {
  type: "chat.send";
  request_id: string;
  conversation_id: string;
  idempotency_key: string;
  content: string;
};
const storageKey = (id: string) => `pending:${id}`;
function readPending(id: string): Pending | null {
  try {
    return JSON.parse(
      sessionStorage.getItem(storageKey(id)) ?? "null",
    ) as Pending | null;
  } catch {
    return null;
  }
}

export function App() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [account, setAccount] = useState<Account | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [messageVersions, setMessageVersions] = useState<
    Record<string, MessageVersion[]>
  >({});
  const [regenerationRetryId, setRegenerationRetryId] = useState<string | null>(
    null,
  );
  const [authMode, setAuthMode] = useState<"login" | "register" | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [selectedProject, setSelectedProject] = useState<string>("");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ApiMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [pageError, setPageError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [canRetry, setCanRetry] = useState(false);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const pendingRef = useRef<Pending | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const bootstrapRef = useRef<Promise<{
    items: Conversation[];
    next_cursor: string | null;
  }> | null>(null);

  useEffect(() => {
    let stopped = false;
    void (async () => {
      try {
        bootstrapRef.current ??= (async () => {
          await ensureSession();
          const signedIn = await currentAccount();
          if (signedIn) {
            setAccount(signedIn);
            setProjects(await listProjects());
          }
          const page = await listConversations();
          if (!page.items.length) page.items = [await createConversation()];
          return page;
        })();
        const page = await bootstrapRef.current;
        const items = page.items;
        if (stopped) return;
        setConversations(items);
        setNextCursor(page.next_cursor);
        const saved = sessionStorage.getItem("activeConversation");
        setActiveId(
          items.some((item) => item.id === saved) ? saved : items[0].id,
        );
      } catch (error) {
        if (!stopped) setPageError(String(error));
      }
    })();
    return () => {
      stopped = true;
    };
  }, []);

  async function reloadConversations(projectId = selectedProject) {
    socketRef.current?.close();
    setConnection("connecting");
    const page = await listConversations(undefined, projectId || undefined);
    if (!page.items.length)
      page.items = [await createConversation(projectId || null)];
    setConversations(page.items);
    setNextCursor(page.next_cursor);
    setActiveId(page.items[0].id);
  }

  async function filterProject(projectId: string) {
    socketRef.current?.close();
    setConnection("connecting");
    setSelectedProject(projectId);
    try {
      const page = await listConversations(undefined, projectId || undefined);
      setConversations(page.items);
      setNextCursor(page.next_cursor);
      setActiveId(page.items[0]?.id ?? null);
    } catch (error) {
      setPageError(String(error));
    }
  }

  async function submitAuth(event: FormEvent) {
    event.preventDefault();
    if (!authMode) return;
    socketRef.current?.close();
    setConnection("connecting");
    try {
      const signedIn = await authenticate(authMode, email, password);
      if (signedIn) window.location.reload();
    } catch (error) {
      setPageError(String(error));
    }
  }

  async function handleClaim() {
    try {
      await claimAnonymous();
      window.location.reload();
    } catch (error) {
      setPageError(String(error));
    }
  }

  async function handleDiscard() {
    if (!window.confirm("Delete all anonymous conversations on this browser?"))
      return;
    try {
      await discardAnonymous();
      window.location.reload();
    } catch (error) {
      setPageError(String(error));
    }
  }

  async function handleLogout() {
    try {
      await logout();
      window.location.reload();
    } catch (error) {
      setPageError(String(error));
    }
  }

  async function handleLogoutAll() {
    try {
      await logoutAll();
      window.location.reload();
    } catch (error) {
      setPageError(String(error));
    }
  }

  async function handleDeleteAccount() {
    if (
      !window.confirm(
        "Delete your account, projects, chats, messages, versions and feedback?",
      )
    )
      return;
    try {
      await deleteAccount();
      window.location.reload();
    } catch (error) {
      setPageError(String(error));
    }
  }

  async function handleCreateProject() {
    const name = window.prompt("Project name");
    if (!name?.trim()) return;
    try {
      const project = await createProject(name.trim());
      setProjects((items) => [...items, project]);
      await filterProject(project.id);
    } catch (error) {
      setPageError(String(error));
    }
  }

  async function handleRenameProject() {
    const project = projects.find((item) => item.id === selectedProject);
    if (!project) return;
    const name = window.prompt("Project name", project.name);
    if (!name?.trim()) return;
    try {
      const updated = await renameProject(project.id, name.trim());
      setProjects((items) =>
        items.map((item) => (item.id === project.id ? updated : item)),
      );
    } catch (error) {
      setPageError(String(error));
    }
  }

  async function handleDeleteProject() {
    if (
      !selectedProject ||
      !window.confirm(
        "Delete this project? Its conversations will become unassigned.",
      )
    )
      return;
    try {
      await deleteProject(selectedProject);
      setProjects((items) =>
        items.filter((item) => item.id !== selectedProject),
      );
      setSelectedProject("");
      await reloadConversations("");
    } catch (error) {
      setPageError(String(error));
    }
  }

  async function handleRename() {
    if (!activeId) return;
    const title = window.prompt("Conversation title", active?.title ?? "");
    if (!title?.trim()) return;
    try {
      const updated = await renameConversation(activeId, title.trim());
      setConversations((items) =>
        items.map((item) => (item.id === activeId ? updated : item)),
      );
    } catch (error) {
      setPageError(String(error));
    }
  }

  async function handleDelete() {
    if (
      !activeId ||
      !window.confirm("Delete this conversation and its messages?")
    )
      return;
    try {
      await deleteConversation(activeId);
      await reloadConversations();
    } catch (error) {
      setPageError(String(error));
    }
  }

  async function handleAssignment(projectId: string) {
    if (!activeId) return;
    try {
      const updated = await assignProject(activeId, projectId || null);
      if (selectedProject && updated.project_id !== selectedProject) {
        await filterProject(selectedProject);
      } else {
        setConversations((items) =>
          items.map((item) => (item.id === activeId ? updated : item)),
        );
      }
    } catch (error) {
      setPageError(String(error));
    }
  }

  async function handleEdit(message: ApiMessage) {
    const content = window.prompt("Edit your message", message.content);
    if (!content?.trim() || !activeId) return;
    try {
      await editMessage(message.id, content.trim());
      setMessages((await getConversation(activeId)).messages);
      setNotice(
        "The earlier answer used the previous prompt. Regenerate it if you want a new answer.",
      );
      setMessageVersions((current) => ({ ...current, [message.id]: [] }));
    } catch (error) {
      setPageError(String(error));
    }
  }

  async function showVersions(message: ApiMessage) {
    try {
      const rows = await listMessageVersions(message.id);
      setMessageVersions((current) => ({ ...current, [message.id]: rows }));
    } catch (error) {
      setPageError(String(error));
    }
  }

  async function restoreVersion(message: ApiMessage, versionId: string) {
    if (!activeId) return;
    try {
      await activateMessageVersion(message.id, versionId);
      setMessages((await getConversation(activeId)).messages);
      setNotice(
        "The earlier answer may use another prompt version. Regenerate it if needed.",
      );
      setMessageVersions((current) => ({ ...current, [message.id]: [] }));
    } catch (error) {
      setPageError(String(error));
    }
  }

  async function giveFeedback(message: ApiMessage, rating: -1 | 1) {
    try {
      const rows = await listMessageVersions(message.id);
      await sendMessageFeedback(message.id, rows[rows.length - 1].id, rating);
    } catch (error) {
      setPageError(String(error));
    }
  }

  async function regenerate(message: ApiMessage) {
    if (!activeId) return;
    const keyName = `regen:${message.id}`;
    const key = sessionStorage.getItem(keyName) ?? crypto.randomUUID();
    sessionStorage.setItem(keyName, key);
    setBusy(true);
    try {
      await regenerateMessage(message.id, key);
      sessionStorage.removeItem(keyName);
      setRegenerationRetryId(null);
      setNotice(null);
      setMessages((await getConversation(activeId)).messages);
    } catch (error) {
      setRegenerationRetryId(message.id);
      setPageError(String(error));
    } finally {
      setBusy(false);
    }
  }

  function startNewRegeneration(message: ApiMessage) {
    sessionStorage.removeItem(`regen:${message.id}`);
    void regenerate(message);
  }

  useEffect(() => {
    if (!activeId) return;
    const id = activeId;
    sessionStorage.setItem("activeConversation", id);
    let stopped = false;
    let timer: number | undefined;
    let poll: number | undefined;
    let retries = 0;
    let assistantId: string | undefined;
    pendingRef.current = readPending(id);
    setBusy(Boolean(pendingRef.current));
    setCanRetry(false);
    setMessages([]);
    setPageError(null);
    setNotice(null);
    const refresh = async () => {
      const conversation = await getConversation(id);
      if (stopped) return;
      setMessages(conversation.messages);
      setConversations((items) =>
        items.map((item) => (item.id === id ? conversation : item)),
      );
    };
    const resume = () => {
      if (
        !stopped &&
        pendingRef.current &&
        socketRef.current?.readyState === WebSocket.OPEN
      ) {
        socketRef.current.send(JSON.stringify(pendingRef.current));
      }
    };
    const finish = () => {
      sessionStorage.removeItem(storageKey(id));
      pendingRef.current = null;
      setBusy(false);
      setCanRetry(false);
    };
    const connect = () => {
      if (stopped) return;
      setConnection("connecting");
      const socket = new WebSocket(websocketUrl());
      socketRef.current = socket;
      socket.onerror = () => {
        if (!stopped) setConnection("error");
      };
      socket.onmessage = (message) => {
        if (stopped) return;
        let event: ServerEvent;
        try {
          event = JSON.parse(String(message.data)) as ServerEvent;
        } catch {
          setPageError("The server returned an invalid response.");
          return;
        }
        if (event.type === "connection.ready") {
          retries = 0;
          void refresh()
            .then(() => {
              if (!stopped) {
                setConnection("open");
                resume();
              }
            })
            .catch((error: unknown) => {
              if (!stopped) setPageError(String(error));
            });
          return;
        }
        if (
          !event.request_id ||
          event.request_id !== pendingRef.current?.request_id
        ) {
          if (event.type === "error")
            setPageError(event.content ?? "Request failed.");
          return;
        }
        if (event.type === "message.started" && event.message_id) {
          assistantId = event.message_id;
          const newMessage: ApiMessage = {
            id: assistantId,
            sequence_number: 0,
            role: "assistant",
            content: "",
            status: "pending",
            error_code: null,
            created_at: new Date().toISOString(),
          };
          setMessages((items) => [
            ...items.filter((item) => item.id !== assistantId),
            newMessage,
          ]);
        } else if (event.type === "message.delta") {
          setMessages((items) =>
            items.map((item) =>
              item.id === assistantId
                ? { ...item, content: item.content + (event.content ?? "") }
                : item,
            ),
          );
        } else if (event.type === "message.completed") {
          finish();
          void refresh().catch((error: unknown) => {
            if (!stopped) setPageError(String(error));
          });
        } else if (event.type === "error") {
          if (event.code === "REQUEST_PENDING") {
            poll = window.setTimeout(resume, 1500);
          } else {
            setPageError(event.content ?? "Request failed.");
            if (!event.retryable) finish();
            else {
              setBusy(false);
              setCanRetry(true);
            }
            void refresh().catch((error: unknown) => {
              if (!stopped) setPageError(String(error));
            });
          }
        }
      };
      socket.onclose = (event) => {
        if (stopped) return;
        setConnection("closed");
        window.clearTimeout(poll);
        if (event.code === 4401 || event.code === 4403) {
          setPageError(
            "Your session expired or this origin is not allowed. Reload to reconnect.",
          );
          return;
        }
        timer = window.setTimeout(
          connect,
          Math.min(1000 * 2 ** retries++, 10000),
        );
      };
    };
    connect();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      window.clearTimeout(poll);
      socketRef.current?.close();
    };
  }, [activeId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function retry() {
    if (socketRef.current?.readyState !== WebSocket.OPEN || !pendingRef.current)
      return;
    setPageError(null);
    setBusy(true);
    setCanRetry(false);
    socketRef.current.send(JSON.stringify(pendingRef.current));
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    if (
      !content ||
      !activeId ||
      busy ||
      pendingRef.current ||
      connection !== "open" ||
      socketRef.current?.readyState !== WebSocket.OPEN
    )
      return;
    const requestId = crypto.randomUUID();
    const pending: Pending = {
      type: "chat.send",
      request_id: requestId,
      conversation_id: activeId,
      idempotency_key: requestId,
      content,
    };
    sessionStorage.setItem(storageKey(activeId), JSON.stringify(pending));
    pendingRef.current = pending;
    setMessages((items) => [
      ...items,
      {
        id: requestId,
        sequence_number: items.length + 1,
        role: "user",
        content,
        status: "completed",
        error_code: null,
        created_at: new Date().toISOString(),
      },
    ]);
    setDraft("");
    retry();
  }

  async function newChat() {
    try {
      socketRef.current?.close();
      setConnection("connecting");
      const conversation = await createConversation(selectedProject || null);
      setConversations((items) => [conversation, ...items]);
      setActiveId(conversation.id);
    } catch (error) {
      setPageError(String(error));
    }
  }

  async function loadMore() {
    if (!nextCursor) return;
    try {
      const page = await listConversations(
        nextCursor,
        selectedProject || undefined,
      );
      setConversations((items) => [
        ...items,
        ...page.items.filter(
          (item) => !items.some((old) => old.id === item.id),
        ),
      ]);
      setNextCursor(page.next_cursor);
    } catch (error) {
      setPageError(String(error));
    }
  }

  const active = conversations.find((item) => item.id === activeId);
  const isReady =
    connection === "open" &&
    socketRef.current?.readyState === WebSocket.OPEN &&
    Boolean(activeId) &&
    !busy &&
    !canRetry;
  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="Conversations">
        <div className="brand">
          <span className="brand-mark">G</span>
          <span>GenAI Chat</span>
        </div>
        <div className="account-controls">
          {account ? (
            <>
              <span>{account.email}</span>
              <button type="button" onClick={() => void handleClaim()}>
                Claim anonymous chats
              </button>
              <button type="button" onClick={() => void handleDiscard()}>
                Discard anonymous chats
              </button>
              <button type="button" onClick={() => void handleLogout()}>
                Log out
              </button>
              <button type="button" onClick={() => void handleLogoutAll()}>
                Log out everywhere
              </button>
              <button type="button" onClick={() => void handleDeleteAccount()}>
                Delete account
              </button>
            </>
          ) : (
            <>
              <button type="button" onClick={() => setAuthMode("login")}>
                Log in
              </button>
              <button type="button" onClick={() => setAuthMode("register")}>
                Create account
              </button>
            </>
          )}
        </div>
        {authMode && (
          <form
            className="auth-form"
            onSubmit={(event) => void submitAuth(event)}
          >
            <h2>{authMode === "login" ? "Log in" : "Create account"}</h2>
            <label>
              Email
              <input
                type="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </label>
            <label>
              Password
              <input
                type="password"
                required
                minLength={12}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            <button type="submit">Continue</button>
            <button type="button" onClick={() => setAuthMode(null)}>
              Cancel
            </button>
          </form>
        )}
        {account && (
          <div className="project-controls">
            <label htmlFor="project-filter">Project</label>
            <select
              id="project-filter"
              value={selectedProject}
              onChange={(event) => void filterProject(event.target.value)}
            >
              <option value="">All projects</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
            <button type="button" onClick={() => void handleCreateProject()}>
              + New project
            </button>
            {selectedProject && (
              <>
                <button
                  type="button"
                  onClick={() => void handleRenameProject()}
                >
                  Rename project
                </button>
                <button
                  type="button"
                  onClick={() => void handleDeleteProject()}
                >
                  Delete project
                </button>
              </>
            )}
          </div>
        )}
        <button
          className="new-chat"
          type="button"
          onClick={() => void newChat()}
        >
          + New conversation
        </button>
        <p className="section-label">Recent</p>
        {conversations.map((conversation) => (
          <button
            className={`conversation ${conversation.id === activeId ? "active" : ""}`}
            key={conversation.id}
            type="button"
            onClick={() => setActiveId(conversation.id)}
          >
            {conversation.title}
          </button>
        ))}
        {nextCursor && (
          <button onClick={() => void loadMore()}>
            Load more conversations
          </button>
        )}
        <div className="sidebar-footer">
          {account ? "Private account chat" : "Private anonymous chat"}
        </div>
      </aside>
      <section className="chat-panel">
        <header className="chat-header">
          <div>
            <h1>{active?.title ?? "Starting chat…"}</h1>
            <p>
              {account
                ? "Private account session"
                : "Private anonymous session"}
            </p>
            <div className="conversation-actions">
              <button
                type="button"
                onClick={() => void handleRename()}
                disabled={!activeId}
              >
                Rename
              </button>
              <button
                type="button"
                onClick={() => void handleDelete()}
                disabled={!activeId}
              >
                Delete
              </button>
              {account && (
                <select
                  aria-label="Assign project"
                  value={active?.project_id ?? ""}
                  onChange={(event) =>
                    void handleAssignment(event.target.value)
                  }
                >
                  <option value="">No project</option>
                  {projects.map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.name}
                    </option>
                  ))}
                </select>
              )}
            </div>
            <div className="mobile-conversations">
              <select
                aria-label="Choose conversation"
                value={activeId ?? ""}
                onChange={(event) => setActiveId(event.target.value)}
              >
                {conversations.map((conversation) => (
                  <option key={conversation.id} value={conversation.id}>
                    {conversation.title}
                  </option>
                ))}
              </select>
              <button type="button" onClick={() => void newChat()}>
                New chat
              </button>
              {nextCursor && (
                <button onClick={() => void loadMore()}>More</button>
              )}
            </div>
          </div>
          <span className={`status ${connection}`} role="status">
            {connection === "open" ? "Connected" : connection}
          </span>
        </header>
        <div className="messages" aria-live="polite">
          <div className="message-list">
            {notice && <p className="chat-notice">{notice}</p>}
            {pageError && (
              <div className="error-banner" role="alert">
                {pageError}
                {canRetry && (
                  <button onClick={retry} disabled={connection !== "open"}>
                    Retry
                  </button>
                )}
                <button onClick={() => window.location.reload()}>Reload</button>
              </div>
            )}
            {!pageError && messages.length === 0 && (
              <div className="empty-state">
                <h2>How can I help?</h2>
                <p>Start a conversation.</p>
              </div>
            )}
            {messages.map((message) => (
              <article className={`message ${message.role}`} key={message.id}>
                <div className="avatar" aria-hidden="true">
                  {message.role === "user" ? "Y" : "G"}
                </div>
                <div className="bubble">
                  <strong>
                    {message.role === "user" ? "You" : "Assistant"}
                  </strong>
                  <p>
                    {message.content ||
                      (message.status === "failed"
                        ? "This request failed. You can send a new message."
                        : "Thinking…")}
                  </p>
                  {message.status === "pending" && (
                    <span className="typing" aria-label="Streaming response" />
                  )}
                  {account && message.status === "completed" && (
                    <div className="message-actions">
                      {message.role === "user" ? (
                        <>
                          <button
                            type="button"
                            onClick={() => void handleEdit(message)}
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={() => void showVersions(message)}
                          >
                            Versions
                          </button>
                          {messageVersions[message.id]?.map((version) => (
                            <button
                              key={version.id}
                              type="button"
                              onClick={() =>
                                void restoreVersion(message, version.id)
                              }
                            >
                              Restore v{version.version_number}
                            </button>
                          ))}
                        </>
                      ) : message.role === "assistant" ? (
                        <>
                          <button
                            type="button"
                            aria-label="Helpful answer"
                            onClick={() => void giveFeedback(message, 1)}
                          >
                            Helpful
                          </button>
                          <button
                            type="button"
                            aria-label="Unhelpful answer"
                            onClick={() => void giveFeedback(message, -1)}
                          >
                            Unhelpful
                          </button>
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => void regenerate(message)}
                          >
                            Regenerate
                          </button>
                          {regenerationRetryId === message.id && (
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => startNewRegeneration(message)}
                            >
                              Start new regeneration
                            </button>
                          )}
                        </>
                      ) : null}
                    </div>
                  )}
                </div>
              </article>
            ))}
            <div ref={bottomRef} />
          </div>
        </div>
        <form className="composer" onSubmit={submit}>
          <label className="sr-only" htmlFor="chat-message">
            Message
          </label>
          <div className="composer-box">
            <textarea
              id="chat-message"
              value={draft}
              maxLength={12000}
              rows={1}
              placeholder={
                isReady
                  ? "Message GenAI Chat…"
                  : "Waiting for connection or response…"
              }
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
            />
            <button
              className="send"
              disabled={!isReady || !draft.trim()}
              aria-label="Send message"
            >
              ↑
            </button>
          </div>
          <p className="composer-hint">
            Enter to send · Shift + Enter for a new line
          </p>
        </form>
      </section>
    </main>
  );
}
