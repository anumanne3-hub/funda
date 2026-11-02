export type ConnectionState = "connecting" | "open" | "closed" | "error";

export type ServerEvent = {
  type: "connection.ready" | "message.started" | "message.delta" | "message.completed" | "error";
  request_id?: string;
  content?: string;
  code?: string;
  retryable?: boolean;
  conversation_id?: string;
  message_id?: string;
};

export function websocketUrl(): string {
  const apiBase = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";
  const url = new URL(apiBase);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = `${url.pathname.replace(/\/$/, "")}/ws/chat`;
  return url.toString();
}
