import { FileCode2, Shield, ShieldAlert, ShieldCheck } from "lucide-react";
import type { RunState } from "../types";

const AGENT_COLORS: Record<string, string> = {
  planner: "bg-purple-900/50 text-purple-300 border-purple-700",
  coder: "bg-blue-900/50 text-blue-300 border-blue-700",
  docker: "bg-cyan-900/50 text-cyan-300 border-cyan-700",
  observability: "bg-teal-900/50 text-teal-300 border-teal-700",
  tester: "bg-yellow-900/50 text-yellow-300 border-yellow-700",
  debugger: "bg-orange-900/50 text-orange-300 border-orange-700",
  reviewer: "bg-indigo-900/50 text-indigo-300 border-indigo-700",
  review_sup: "bg-slate-700/50 text-slate-300 border-slate-600",
  security: "bg-red-900/50 text-red-300 border-red-700",
  perf: "bg-amber-900/50 text-amber-300 border-amber-700",
  style: "bg-pink-900/50 text-pink-300 border-pink-700",
  coverage: "bg-emerald-900/50 text-emerald-300 border-emerald-700",
};

const SEVERITY_STYLES: Record<string, string> = {
  critical: "bg-red-900/60 border-red-700 text-red-300",
  major: "bg-orange-900/60 border-orange-700 text-orange-300",
  minor: "bg-yellow-900/60 border-yellow-700 text-yellow-300",
  info: "bg-gray-800 border-gray-700 text-gray-400",
};

function fmt(n: number, digits = 2) {
  return n.toLocaleString(undefined, { maximumFractionDigits: digits });
}

interface Props {
  runState: RunState;
}

export function StreamPanel({ runState }: Props) {
  const { steps, budget, artifacts, findings } = runState;

  const tokenPct = budget
    ? Math.min(100, (budget.tokens_used / 2_000_000) * 100)
    : 0;
  const costPct = budget
    ? Math.min(100, (budget.cost_used_usd / 5.0) * 100)
    : 0;

  return (
    <div className="flex flex-col gap-4 h-full overflow-y-auto pr-1">
      {/* Budget meters */}
      {budget && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-widest">Budget</h3>
          <div>
            <div className="flex justify-between text-xs text-gray-400 mb-1">
              <span>Tokens</span>
              <span>{fmt(budget.tokens_used / 1000, 0)}K / 2,000K</span>
            </div>
            <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-orange-500 rounded-full transition-all"
                style={{ width: `${tokenPct}%` }}
              />
            </div>
          </div>
          <div>
            <div className="flex justify-between text-xs text-gray-400 mb-1">
              <span>Cost</span>
              <span>${fmt(budget.cost_used_usd, 4)} / $5.00</span>
            </div>
            <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  costPct > 80 ? "bg-red-500" : costPct > 50 ? "bg-yellow-500" : "bg-green-500"
                }`}
                style={{ width: `${costPct}%` }}
              />
            </div>
          </div>
          <div className="text-xs text-gray-500">Steps: {budget.steps_taken}</div>
        </div>
      )}

      {/* CoT step log */}
      {steps.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">
            Agent Steps
          </h3>
          <div className="space-y-2">
            {steps.map((s, i) => {
              const color = AGENT_COLORS[s.agent] ?? "bg-gray-800 text-gray-300 border-gray-700";
              return (
                <div
                  key={i}
                  className={`flex items-center gap-2 text-xs rounded-lg border px-3 py-2 ${color}`}
                >
                  <span className="font-mono font-semibold w-5 text-right">{s.step}</span>
                  <span className="font-semibold min-w-[90px]">{s.agent}</span>
                  <span className="text-gray-500 font-mono">{fmt(s.tokens / 1000, 1)}K tok</span>
                  <span className="text-gray-500 font-mono">${fmt(s.cost_usd, 4)}</span>
                  <span className="text-gray-600 font-mono ml-auto">{fmt(s.latency_s, 2)}s</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Modified files */}
      {artifacts.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">
            Files Modified ({artifacts.length})
          </h3>
          <div className="space-y-1">
            {artifacts.map((a, i) => (
              <div key={i} className="flex items-center gap-2 text-xs text-gray-400">
                <FileCode2 size={12} className="shrink-0 text-gray-600" />
                <span className="font-mono truncate">{a.path}</span>
                <span className="ml-auto text-gray-600 shrink-0">{a.kind}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Findings */}
      {findings.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3 flex items-center gap-2">
            <Shield size={12} />
            Review Findings ({findings.length})
          </h3>
          <div className="space-y-1.5">
            {findings.map((f, i) => (
              <div
                key={i}
                className={`text-xs rounded-lg border px-3 py-2 ${SEVERITY_STYLES[f.severity] ?? SEVERITY_STYLES.info}`}
              >
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="font-semibold uppercase">{f.severity}</span>
                  <span className="text-gray-500">·</span>
                  <span className="text-gray-400">{f.agent}</span>
                </div>
                <div className="text-gray-300">{f.message}</div>
                <div className="text-gray-500 font-mono mt-0.5">{f.location}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Empty state */}
      {steps.length === 0 && artifacts.length === 0 && findings.length === 0 && !budget && (
        <div className="flex-1 flex items-center justify-center text-gray-700 text-sm">
          Agent output will stream here…
        </div>
      )}
    </div>
  );
}
