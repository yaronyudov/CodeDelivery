import type { Skill } from "../types";

const BASE = "/api/skills";

export async function listSkills(): Promise<Skill[]> {
  const res = await fetch(BASE, { credentials: "include" });
  if (!res.ok) throw new Error("Failed to load skills");
  return res.json();
}

export async function getSkill(id: string): Promise<Skill> {
  const res = await fetch(`${BASE}/${id}`, { credentials: "include" });
  if (!res.ok) throw new Error("Failed to load skill");
  return res.json();
}

export async function createSkill(skill: Omit<Skill, "is_system" | "created_at">): Promise<Skill> {
  const res = await fetch(BASE, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(skill),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to create skill");
  }
  return res.json();
}

export async function updateSkill(
  id: string,
  updates: Partial<Pick<Skill, "name" | "description" | "target_agents" | "prompt_addon" | "is_default">>,
): Promise<Skill> {
  const res = await fetch(`${BASE}/${id}`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to update skill");
  }
  return res.json();
}

export async function deleteSkill(id: string): Promise<void> {
  const res = await fetch(`${BASE}/${id}`, { method: "DELETE", credentials: "include" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to delete skill");
  }
}

export async function toggleSkillDefault(id: string): Promise<Skill> {
  const res = await fetch(`${BASE}/${id}/default`, {
    method: "PATCH",
    credentials: "include",
  });
  if (!res.ok) throw new Error("Failed to toggle default");
  return res.json();
}
