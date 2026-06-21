import { useState } from "react";
import { Play, Square } from "lucide-react";
import { startRun, stopRun } from "../api/runs";
import type { ModelConfig, Skill, SessionSkillOverrides } from "../types";
import { ModelPicker } from "./ModelPicker";
import { SessionSkills } from "./SessionSkills";

interface Props {
  runId: string | null;
  runStatus: string;
  onStart: (runId: string) => void;
  onStop: () => void;
  requireApproval: boolean;
  onRequireApprovalChange: (v: boolean) => void;
  skills: Skill[];
  skillOverrides: SessionSkillOverrides;
  onSkillOverridesChange: (o: SessionSkillOverrides) => void;
}

const DEFAULT_MODEL: ModelConfig = {
  provider: "anthropic",
  model: "anthropic/claude-sonnet-4-6",
};

export function ChatWindow({
  runId,
  runStatus,
  onStart,
  onStop,
  requireApproval,
  onRequireApprovalChange,
  skills,
  skillOverrides,
  onSkillOverridesChange,
}: Props) {
  const [text, setText] = useState("");
  const [modelConfig, setModelConfig] = useState<ModelConfig>(DEFAULT_MODEL);
  const [error, setError] = useState<string | null>(null);

  const isRunning = runStatus === "running";

  async function handleExecute() {
    if (!text.trim()) return;
    setError(null);
    try {
      const { run_id } = await startRun(text.trim(), modelConfig, requireApproval, skillOverrides);
      onStart(run_id);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to start run");
    }
  }

  async function handleStop() {
    if (!runId) return;
    await stopRun(runId);
    onStop();
  }

  return (
    <div className="bg-gray-900 border-t border-gray-800 px-4 py-4">
      {error && (
        <div className="bg-red-900/40 border border-red-700 text-red-300 rounded-lg p-3 mb-3 text-sm">
          {error}
        </div>
      )}

      {/* Controls row */}
      <div className="flex flex-wrap items-center gap-3 mb-3">
        <ModelPicker value={modelConfig} onChange={setModelConfig} />

        <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer ml-auto">
          <input
            type="checkbox"
            checked={requireApproval}
            onChange={(e) => onRequireApprovalChange(e.target.checked)}
            className="rounded border-gray-600 bg-gray-800 text-orange-500 focus:ring-orange-500"
          />
          Require human approval before coding
        </label>
      </div>

      {/* Session skill overrides */}
      <div className="mb-3">
        <SessionSkills
          skills={skills}
          overrides={skillOverrides}
          onChange={onSkillOverridesChange}
        />
      </div>

      {/* Textarea + action buttons */}
      <div className="flex gap-2">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={isRunning}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && !isRunning) handleExecute();
          }}
          placeholder="Describe the feature you want built…"
          rows={3}
          className="flex-1 bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 text-gray-100 placeholder-gray-600 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent"
        />

        <div className="flex flex-col gap-2">
          <button
            onClick={handleExecute}
            disabled={isRunning || !text.trim()}
            title="Execute (Ctrl+Enter)"
            className="flex items-center gap-1.5 px-4 py-2 bg-orange-500 hover:bg-orange-600 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold rounded-xl text-sm transition-colors"
          >
            <Play size={14} />
            Execute
          </button>

          <button
            onClick={handleStop}
            disabled={!isRunning}
            className="flex items-center gap-1.5 px-4 py-2 bg-gray-700 hover:bg-red-800 disabled:opacity-30 disabled:cursor-not-allowed text-gray-300 hover:text-white font-semibold rounded-xl text-sm transition-colors"
          >
            <Square size={14} />
            Stop
          </button>
        </div>
      </div>
    </div>
  );
}
