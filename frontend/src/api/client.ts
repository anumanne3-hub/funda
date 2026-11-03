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
  project_id: string | null;
  created_at: string;
  updated_at: string;
  messages: ApiMessage[];
};

const baseUrl =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

let csrfToken: string | null = null;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = init?.method?.toUpperCase() ?? "GET";
  if (
    !["GET", "HEAD"].includes(method) &&
    csrfToken &&
    !path.startsWith("/auth/login") &&
    !path.startsWith("/auth/register")
  ) {
    init = {
      ...init,
      headers: { "X-CSRF-Token": csrfToken, ...init?.headers },
    };
  }
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      message?: string;
    } | null;
    throw new Error(body?.message ?? `API request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export type Account = { id: string; email: string };
export type Project = { id: string; name: string };
export type MessageVersion = {
  id: string;
  message_id: string;
  version_number: number;
  parent_version_id: string | null;
  content: string;
};

export async function currentAccount(): Promise<Account | null> {
  try {
    const account = await request<Account>("/auth/me");
    csrfToken = (await request<{ csrf_token: string }>("/auth/csrf"))
      .csrf_token;
    return account;
  } catch {
    csrfToken = null;
    return null;
  }
}

export async function authenticate(
  mode: "login" | "register",
  email: string,
  password: string,
): Promise<Account> {
  const account = await request<Account>(`/auth/${mode}`, {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  csrfToken = (await request<{ csrf_token: string }>("/auth/csrf")).csrf_token;
  return account;
}

export async function logout(): Promise<void> {
  await request<void>("/auth/logout", { method: "POST" });
  csrfToken = null;
}

export async function logoutAll(): Promise<void> {
  await request<void>("/auth/logout-all", { method: "POST" });
  csrfToken = null;
}

export async function deleteAccount(): Promise<void> {
  await request<void>("/auth/account", { method: "DELETE" });
  csrfToken = null;
}

export async function claimAnonymous(): Promise<number> {
  return (
    await request<{ claimed: number }>("/auth/claim-anonymous", {
      method: "POST",
    })
  ).claimed;
}

export async function discardAnonymous(): Promise<void> {
  await request<void>("/auth/discard-anonymous", { method: "POST" });
}

export async function listProjects(): Promise<Project[]> {
  return request("/projects");
}
export async function createProject(name: string): Promise<Project> {
  return request("/projects", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}
export async function renameProject(
  id: string,
  name: string,
): Promise<Project> {
  return request(`/projects/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}
export async function deleteProject(id: string): Promise<void> {
  await request<void>(`/projects/${id}`, { method: "DELETE" });
}
export async function renameConversation(
  id: string,
  title: string,
): Promise<Conversation> {
  return request(`/conversations/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
}
export async function deleteConversation(id: string): Promise<void> {
  await request(`/conversations/${id}`, { method: "DELETE" });
}
export async function assignProject(
  id: string,
  projectId: string | null,
): Promise<Conversation> {
  return request(`/conversations/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ project_id: projectId }),
  });
}

export async function listMessageVersions(
  id: string,
): Promise<MessageVersion[]> {
  return request(`/messages/${id}/versions`);
}

export async function editMessage(
  id: string,
  content: string,
): Promise<MessageVersion> {
  return request(`/messages/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ content }),
  });
}

export async function activateMessageVersion(
  id: string,
  versionId: string,
): Promise<MessageVersion> {
  return request(`/messages/${id}/activate/${versionId}`, { method: "POST" });
}

export async function sendMessageFeedback(
  id: string,
  versionId: string,
  rating: -1 | 1,
): Promise<void> {
  await request(`/messages/${id}/feedback`, {
    method: "POST",
    body: JSON.stringify({ version_id: versionId, rating }),
  });
}

export async function regenerateMessage(
  id: string,
  idempotencyKey: string,
): Promise<MessageVersion> {
  return request(`/messages/${id}/regenerate`, {
    method: "POST",
    body: JSON.stringify({ idempotency_key: idempotencyKey }),
  });
}

export async function ensureSession(): Promise<void> {
  await request("/anonymous-session", { method: "POST" });
}

export async function listConversations(
  cursor?: string,
  projectId?: string,
): Promise<{ items: Conversation[]; next_cursor: string | null }> {
  return request(
    `/conversations?limit=20${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}${projectId ? `&project_id=${encodeURIComponent(projectId)}` : ""}`,
  );
}

export async function createConversation(
  projectId?: string | null,
): Promise<Conversation> {
  return request("/conversations", {
    method: "POST",
    body: JSON.stringify({
      title: "New conversation",
      project_id: projectId ?? null,
    }),
  });
}

export async function getConversation(id: string): Promise<Conversation> {
  return request(`/conversations/${id}`);
}
