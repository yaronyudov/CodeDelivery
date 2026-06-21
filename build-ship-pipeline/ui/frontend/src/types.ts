export type Provider = "anthropic" | "openai" | "groq" | "ollama" | "custom";

export interface ModelConfig {
  provider: Provider;
  model: string;
  api_base?: string;
  api_key?: string;
}

export interface RunSummary {
  run_id: string;
  feature_request: string;
  status: "running" | "done" | "halted" | "stopped";
  verdict: string | null;
  require_approval: boolean;
  created_at: string;
  finished_at: string | null;
}

// WebSocket event types
export type WSEvent =
  | { type: "step"; agent: string; phase: string; step: number; tokens: number; cost_usd: number; latency_s: number }
  | { type: "budget"; tokens_used: number; cost_used_usd: number; steps_taken: number }
  | { type: "artifact"; path: string; kind: string }
  | { type: "finding"; severity: "critical" | "major" | "minor" | "info"; agent: string; message: string; location: string }
  | { type: "approval_required"; plan: object }
  | { type: "halt"; reason: string }
  | { type: "done"; verdict: string; cost_total: number }
  | { type: "error"; message: string }
  | { type: "ping" };

export interface RunState {
  runId: string | null;
  status: "idle" | "running" | "done" | "halted" | "stopped";
  steps: Extract<WSEvent, { type: "step" }>[];
  budget: Extract<WSEvent, { type: "budget" }> | null;
  artifacts: Extract<WSEvent, { type: "artifact" }>[];
  findings: Extract<WSEvent, { type: "finding" }>[];
  approvalRequired: boolean;
  approvalPlan: object | null;
  haltReason: string | null;
  verdict: string | null;
}
