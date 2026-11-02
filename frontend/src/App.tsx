import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  createConversation,
  ensureSession,
  getConversation,
  listConversations,
} from "./api/client";
import type { ApiMessage, Conversation } from "./api/client";
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
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ApiMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [pageError, setPageError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const pendingRef = useRef<Pending | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let stopped = false;
    void (async () => {
      try {
        await ensureSession();
        const page = await listConversations();
        const items = page.items.length
          ? page.items
          : [await createConversation()];
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
    setMessages([]);
    setPageError(null);
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
          setConnection("open");
          void refresh()
            .then(resume)
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
            else setBusy(false);
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

  useEffect(
    () => bottomRef.current?.scrollIntoView({ behavior: "smooth" }),
    [messages],
  );

  function retry() {
    if (socketRef.current?.readyState !== WebSocket.OPEN || !pendingRef.current)
      return;
    setPageError(null);
    setBusy(true);
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
      connection !== "open"
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
      const conversation = await createConversation();
      setConversations((items) => [conversation, ...items]);
      setActiveId(conversation.id);
    } catch (error) {
      setPageError(String(error));
    }
  }

  async function loadMore() {
    if (!nextCursor) return;
    try {
      const page = await listConversations(nextCursor);
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
  const isReady = connection === "open" && Boolean(activeId) && !busy;
  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="Conversations">
        <div className="brand">
          <span className="brand-mark">G</span>
          <span>GenAI Chat</span>
        </div>
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
        <div className="sidebar-footer">Private anonymous chat</div>
      </aside>
      <section className="chat-panel">
        <header className="chat-header">
          <div>
            <h1>{active?.title ?? "Starting chat…"}</h1>
            <p>Private anonymous session</p>
          </div>
          <span className={`status ${connection}`} role="status">
            {connection === "open" ? "Connected" : connection}
          </span>
        </header>
        <div className="messages" aria-live="polite">
          <div className="message-list">
            {pageError && (
              <div className="error-banner" role="alert">
                {pageError}
                {!busy && (
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
