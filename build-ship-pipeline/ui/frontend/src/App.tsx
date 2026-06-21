import { useEffect, useState } from "react";
import { getMe } from "./api/auth";
import { listSkills } from "./api/skills";
import { ApprovalGate } from "./components/ApprovalGate";
import { ChatWindow } from "./components/ChatWindow";
import { Login } from "./components/Login";
import { Sidebar } from "./components/Sidebar";
import { SkillsManager } from "./components/SkillsManager";
import { StreamPanel } from "./components/StreamPanel";
import { useRun } from "./hooks/useRun";
import { useWebSocket } from "./hooks/useWebSocket";
import type { RunSummary, Skill, SessionSkillOverrides } from "./types";

type AuthState = "loading" | "authed" | "anon";

export default function App() {
  const [auth, setAuth] = useState<AuthState>("loading");
  const [username, setUsername] = useState("");
  const [requireApproval, setRequireApproval] = useState(false);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [skillOverrides, setSkillOverrides] = useState<SessionSkillOverrides>({});
  const [showSkillsManager, setShowSkillsManager] = useState(false);

  const { state: runState, start, onEvent, reset } = useRun();
  useWebSocket(runState.runId, onEvent);

  useEffect(() => {
    getMe().then((user) => {
      if (user) {
        setUsername(user.username);
        setAuth("authed");
      } else {
        setAuth("anon");
      }
    });
  }, []);

  useEffect(() => {
    if (auth === "authed") {
      listSkills().then(setSkills).catch(() => {});
    }
  }, [auth]);

  function handleLoginSuccess() {
    getMe().then((user) => {
      if (user) {
        setUsername(user.username);
        setAuth("authed");
      }
    });
  }

  function handleSelectRun(run: RunSummary) {
    reset();
    start(run.run_id);
  }

  if (auth === "loading") {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center text-gray-600">
        Loading…
      </div>
    );
  }

  if (auth === "anon") {
    return <Login onSuccess={handleLoginSuccess} />;
  }

  return (
    <div className="flex h-screen overflow-hidden bg-gray-950">
      <Sidebar
        activeRunId={runState.runId}
        onSelectRun={handleSelectRun}
        onNewRun={reset}
        username={username}
        onOpenSkillsManager={() => setShowSkillsManager(true)}
      />

      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Status bar */}
        {runState.runId && (
          <div className="px-6 py-2 border-b border-gray-800 text-xs text-gray-500 flex items-center gap-2">
            <span>Run</span>
            <code className="font-mono text-gray-400">{runState.runId.slice(0, 8)}</code>
            <span className={`
              ml-1 px-2 py-0.5 rounded-full text-xs font-semibold
              ${runState.status === "running" ? "bg-orange-900/40 text-orange-300" : ""}
              ${runState.status === "done" ? "bg-green-900/40 text-green-300" : ""}
              ${runState.status === "halted" ? "bg-red-900/40 text-red-300" : ""}
              ${runState.status === "idle" ? "hidden" : ""}
            `}>
              {runState.status}
            </span>
            {runState.verdict && (
              <span className="ml-2 text-gray-400">verdict: <strong>{runState.verdict}</strong></span>
            )}
            {runState.haltReason && (
              <span className="ml-2 text-red-400">— {runState.haltReason}</span>
            )}
          </div>
        )}

        {/* Stream area */}
        <div className="flex-1 overflow-y-auto p-6">
          <StreamPanel runState={runState} />
        </div>

        {/* Chat input */}
        <ChatWindow
          runId={runState.runId}
          runStatus={runState.status}
          onStart={(id) => start(id)}
          onStop={() => {}}
          requireApproval={requireApproval}
          onRequireApprovalChange={setRequireApproval}
          skills={skills}
          skillOverrides={skillOverrides}
          onSkillOverridesChange={setSkillOverrides}
        />
      </main>

      {/* Approval modal */}
      {runState.approvalRequired && runState.approvalPlan && runState.runId && (
        <ApprovalGate
          runId={runState.runId}
          plan={runState.approvalPlan}
          onDecision={() =>
            onEvent({ type: "step", agent: "approval_gate", phase: "dev", step: 0, tokens: 0, cost_usd: 0, latency_s: 0 })
          }
        />
      )}

      {/* Skills manager slide-over */}
      {showSkillsManager && (
        <SkillsManager
          onClose={() => {
            setShowSkillsManager(false);
            listSkills().then(setSkills).catch(() => {});
          }}
        />
      )}
    </div>
  );
}
