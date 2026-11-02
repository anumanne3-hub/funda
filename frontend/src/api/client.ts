export type ApiMessage = {
  id: string;
  sequence_number: number;
  role: "user" | "assistant" | "system";
  content: string;
  status: "pending" | "completed" | "failed";
  error_code: string | null;
  created_at: string;
};

export type Conversation = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: ApiMessage[];
};

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) throw new Error(`API request failed (${response.status})`);
  return response.json() as Promise<T>;
}

export async function ensureSession(): Promise<void> {
  await request("/anonymous-session", { method: "POST" });
}

export async function listConversations(cursor?: string): Promise<{ items: Conversation[]; next_cursor: string | null }> {
  return request(`/conversations?limit=20${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`);
}

export async function createConversation(): Promise<Conversation> {
  return request("/conversations", {
    method: "POST",
    body: JSON.stringify({ title: "New conversation" }),
  });
}

export async function getConversation(id: string): Promise<Conversation> {
  return request(`/conversations/${id}`);
}
