import { useCallback, useReducer } from "react";
import type { RunState, WSEvent } from "../types";

const INITIAL: RunState = {
  runId: null,
  status: "idle",
  steps: [],
  budget: null,
  artifacts: [],
  findings: [],
  approvalRequired: false,
  approvalPlan: null,
  haltReason: null,
  verdict: null,
};

type Action =
  | { type: "START"; runId: string }
  | { type: "EVENT"; event: WSEvent }
  | { type: "RESET" };

function reducer(state: RunState, action: Action): RunState {
  switch (action.type) {
    case "START":
      return { ...INITIAL, runId: action.runId, status: "running" };

    case "RESET":
      return INITIAL;

    case "EVENT": {
      const ev = action.event;
      switch (ev.type) {
        case "step":
          return { ...state, steps: [...state.steps, ev] };
        case "budget":
          return { ...state, budget: ev };
        case "artifact":
          return { ...state, artifacts: [...state.artifacts, ev] };
        case "finding":
          return { ...state, findings: [...state.findings, ev] };
        case "approval_required":
          return { ...state, approvalRequired: true, approvalPlan: ev.plan };
        case "halt":
          return { ...state, status: "halted", haltReason: ev.reason };
        case "done":
          return { ...state, status: "done", verdict: ev.verdict };
        default:
          return state;
      }
    }
  }
}

export function useRun() {
  const [state, dispatch] = useReducer(reducer, INITIAL);

  const start = useCallback((runId: string) => dispatch({ type: "START", runId }), []);
  const onEvent = useCallback((event: WSEvent) => dispatch({ type: "EVENT", event }), []);
  const reset = useCallback(() => dispatch({ type: "RESET" }), []);

  return { state, start, onEvent, reset };
}
