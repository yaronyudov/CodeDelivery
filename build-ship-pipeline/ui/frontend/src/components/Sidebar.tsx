import { useEffect, useState } from "react";
import { CheckCircle, Clock, PlusCircle, Settings, XCircle } from "lucide-react";
import { logout } from "../api/auth";
import { listRuns } from "../api/runs";
import type { RunSummary } from "../types";

interface Props {
  activeRunId: string | null;
  onSelectRun: (run: RunSummary) => void;
  onNewRun: () => void;
  username: string;
  onOpenSkillsManager?: () => void;
}

function StatusIcon({ status }: { status: RunSummary["status"] }) {
  if (status === "done") return <CheckCircle size={14} className="text-green-400 shrink-0" />;
  if (status === "running") return <Clock size={14} className="text-orange-400 shrink-0 animate-spin" />;
  return <XCircle size={14} className="text-red-400 shrink-0" />;
}

export function Sidebar({ activeRunId, onSelectRun, onNewRun, username, onOpenSkillsManager }: Props) {
  const [runs, setRuns] = useState<RunSummary[]>([]);

  useEffect(() => {
    listRuns().then(setRuns).catch(() => {});
    const interval = setInterval(() => listRuns().then(setRuns).catch(() => {}), 5000);
    return () => clearInterval(interval);
  }, [activeRunId]);

  async function handleLogout() {
    await logout();
    window.location.reload();
  }

  return (
    <aside className="w-64 shrink-0 bg-gray-900 border-r border-gray-800 flex flex-col h-screen">
      {/* Logo */}
      <div className="px-4 py-4 border-b border-gray-800">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-widest">Build & Ship</p>
      </div>

      {/* New run button */}
      <div className="p-3">
        <button
          onClick={onNewRun}
          className="w-full flex items-center gap-2 text-sm text-gray-300 hover:text-white hover:bg-gray-800 rounded-lg px-3 py-2 transition-colors"
        >
          <PlusCircle size={16} />
          New run
        </button>
      </div>

      {/* Run list */}
      <nav className="flex-1 overflow-y-auto px-2 space-y-0.5 pb-4">
        {runs.length === 0 && (
          <p className="text-xs text-gray-600 px-3 py-2">No runs yet.</p>
        )}
        {runs.map((run) => (
          <button
            key={run.run_id}
            onClick={() => onSelectRun(run)}
            className={`w-full text-left flex items-start gap-2 px-3 py-2 rounded-lg transition-colors text-sm ${
              run.run_id === activeRunId
                ? "bg-gray-800 text-white"
                : "text-gray-400 hover:text-gray-200 hover:bg-gray-800/60"
            }`}
          >
            <StatusIcon status={run.status} />
            <span className="truncate leading-snug">{run.feature_request}</span>
          </button>
        ))}
      </nav>

      {/* User footer */}
      <div className="border-t border-gray-800 px-4 py-3 flex items-center justify-between">
        <span className="text-sm text-gray-400 truncate">{username}</span>
        <div className="flex items-center gap-2 ml-2">
          {onOpenSkillsManager && (
            <button
              onClick={onOpenSkillsManager}
              title="Manage skills"
              className="text-gray-600 hover:text-orange-400 transition-colors"
            >
              <Settings size={15} />
            </button>
          )}
          <button
            onClick={handleLogout}
            className="text-xs text-gray-600 hover:text-red-400 transition-colors"
          >
            Sign out
          </button>
        </div>
      </div>
    </aside>
  );
}
