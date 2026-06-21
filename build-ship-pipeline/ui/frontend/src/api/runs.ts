import type { ModelConfig, RunSummary } from "../types";

const BASE = "/api/runs";

export async function listRuns(): Promise<RunSummary[]> {
  const res = await fetch(BASE, { credentials: "include" });
  if (!res.ok) throw new Error("Failed to load runs");
  return res.json();
}

export async function startRun(
  feature_request: string,
  model_config: ModelConfig,
  require_approval: boolean,
): Promise<{ run_id: string }> {
  const res = await fetch(BASE, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ feature_request, model_config, require_approval }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to start run");
  }
  return res.json();
}

export async function stopRun(run_id: string): Promise<void> {
  await fetch(`${BASE}/${run_id}/stop`, { method: "POST", credentials: "include" });
}

export async function approveRun(run_id: string, approved: boolean): Promise<void> {
  await fetch(`${BASE}/${run_id}/approve`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved }),
  });
}
