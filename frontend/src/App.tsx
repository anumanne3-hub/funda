import { FormEvent, useEffect, useRef, useState } from "react";
import { ConnectionState, ServerEvent, websocketUrl } from "./api/chatSocket";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  status: "streaming" | "completed" | "failed";
};

const welcome: Message = {
  id: "welcome",
  role: "assistant",
  content: "Hello. I’m your project assistant. What would you like to work on?",
  status: "completed",
};

export function App() {
  const [messages, setMessages] = useState<Message[]>([welcome]);
  const [draft, setDraft] = useState("");
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const socketRef = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const socket = new WebSocket(websocketUrl());
    socketRef.current = socket;
    socket.onopen = () => setConnection("open");
    socket.onerror = () => setConnection("error");
    socket.onclose = () => setConnection("closed");
    socket.onmessage = (message) => handleServerEvent(JSON.parse(message.data) as ServerEvent);
    return () => socket.close();
  }, []);

  useEffect(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), [messages]);

  function handleServerEvent(event: ServerEvent) {
    if (!event.request_id) return;
    if (event.type === "message.started") {
      setMessages((current) => [
        ...current,
        { id: event.request_id!, role: "assistant", content: "", status: "streaming" },
      ]);
    } else if (event.type === "message.delta") {
      setMessages((current) =>
        current.map((item) =>
          item.id === event.request_id ? { ...item, content: item.content + (event.content ?? "") } : item,
        ),
      );
    } else if (event.type === "message.completed") {
      setMessages((current) =>
        current.map((item) => item.id === event.request_id ? { ...item, status: "completed" } : item),
      );
    } else if (event.type === "error") {
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: event.content ?? "The request failed. Please try again.",
          status: "failed",
        },
      ]);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || connection !== "open" || !socketRef.current) return;
    const requestId = crypto.randomUUID();
    setMessages((current) => [
      ...current,
      { id: `user-${requestId}`, role: "user", content, status: "completed" },
    ]);
    socketRef.current.send(JSON.stringify({ type: "chat.send", request_id: requestId, content }));
    setDraft("");
  }

  const isReady = connection === "open";

  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="Conversations">
        <div className="brand"><span className="brand-mark">G</span><span>GenAI Chat</span></div>
        <button className="new-chat" type="button">＋ New conversation</button>
        <p className="section-label">Recent</p>
        <button className="conversation active" type="button">Getting started</button>
        <div className="sidebar-footer">Milestone 1 · Mock provider</div>
      </aside>

      <section className="chat-panel">
        <header className="chat-header">
          <div><h1>Getting started</h1><p>Simple, private-by-session chat</p></div>
          <span className={`status ${connection}`} role="status">
            <span className="status-dot" /> {connection === "open" ? "Connected" : connection}
          </span>
        </header>

        <div className="messages" aria-live="polite">
          <div className="message-list">
            {messages.map((message) => (
              <article className={`message ${message.role}`} key={message.id}>
                <div className="avatar" aria-hidden="true">{message.role === "user" ? "Y" : "G"}</div>
                <div className="bubble">
                  <strong>{message.role === "user" ? "You" : "Assistant"}</strong>
                  <p>{message.content || "Thinking…"}</p>
                  {message.status === "streaming" && <span className="typing" aria-label="Streaming response" />}
                </div>
              </article>
            ))}
            <div ref={bottomRef} />
          </div>
        </div>

        <form className="composer" onSubmit={submit}>
          <label className="sr-only" htmlFor="chat-message">Message</label>
          <div className="composer-box">
            <textarea
              id="chat-message"
              value={draft}
              maxLength={12000}
              rows={1}
              placeholder={isReady ? "Message GenAI Chat…" : "Connecting to chat…"}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
            />
            <button className="send" disabled={!isReady || !draft.trim()} aria-label="Send message">↑</button>
          </div>
          <p className="composer-hint">Enter to send · Shift + Enter for a new line</p>
        </form>
      </section>
    </main>
  );
}
