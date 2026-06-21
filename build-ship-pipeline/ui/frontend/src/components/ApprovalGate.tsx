import { CheckCircle, XCircle } from "lucide-react";
import { approveRun } from "../api/runs";

interface Props {
  runId: string;
  plan: object;
  onDecision: () => void;
}

export function ApprovalGate({ runId, plan, onDecision }: Props) {
  async function decide(approved: boolean) {
    await approveRun(runId, approved);
    onDecision();
  }

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-xl shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col">
        <div className="px-6 py-4 border-b border-gray-800">
          <h2 className="text-lg font-semibold text-white">Review Plan Before Coding</h2>
          <p className="text-sm text-gray-400 mt-1">The planner has generated a build plan. Approve to start coding or reject to halt.</p>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4">
          <pre className="text-xs text-gray-300 bg-gray-950 rounded-lg p-4 overflow-x-auto whitespace-pre-wrap">
            {JSON.stringify(plan, null, 2)}
          </pre>
        </div>

        <div className="px-6 py-4 border-t border-gray-800 flex gap-3 justify-end">
          <button
            onClick={() => decide(false)}
            className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-red-900/50 border border-gray-700 hover:border-red-700 text-gray-300 hover:text-red-300 rounded-lg text-sm font-medium transition-colors"
          >
            <XCircle size={16} />
            Reject
          </button>
          <button
            onClick={() => decide(true)}
            className="flex items-center gap-2 px-4 py-2 bg-green-700 hover:bg-green-600 text-white rounded-lg text-sm font-medium transition-colors"
          >
            <CheckCircle size={16} />
            Approve &amp; Start Coding
          </button>
        </div>
      </div>
    </div>
  );
}
