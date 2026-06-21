import { useCallback, useEffect, useRef } from "react";
import type { WSEvent } from "../types";

export function useWebSocket(
  runId: string | null,
  onEvent: (event: WSEvent) => void,
) {
  const wsRef = useRef<WebSocket | null>(null);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  const connect = useCallback((id: string) => {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${protocol}://${window.location.host}/ws/runs/${id}`);
    wsRef.current = ws;

    ws.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data) as WSEvent;
        if (event.type !== "ping") onEventRef.current(event);
      } catch {
        // ignore malformed frames
      }
    };

    ws.onerror = () => {
      onEventRef.current({ type: "error", message: "WebSocket connection error" });
    };

    ws.onclose = () => {
      wsRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!runId) return;
    connect(runId);
    return () => {
      wsRef.current?.close();
    };
  }, [runId, connect]);
}
