const BASE = "/api/auth";

export async function login(username: string, password: string): Promise<void> {
  const res = await fetch(`${BASE}/login`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Login failed");
  }
}

export async function logout(): Promise<void> {
  await fetch(`${BASE}/logout`, { method: "POST", credentials: "include" });
}

export async function getMe(): Promise<{ username: string; user_id: number } | null> {
  const res = await fetch(`${BASE}/me`, { credentials: "include" });
  if (!res.ok) return null;
  return res.json();
}
