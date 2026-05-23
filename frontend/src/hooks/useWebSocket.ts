import { useEffect, useRef, useState, useCallback } from "react";
import type { ProgressEvent, DataInsight, ContentChange } from "../types";
import { createWsUrl } from "../api/client";

export function useWebSocket(taskId: string | undefined) {
  const [lastMessage, setLastMessage] = useState<ProgressEvent | null>(null);
  const [connected, setConnected] = useState(false);
  const [insights, setInsights] = useState<DataInsight[]>([]);
  const [changes, setChanges] = useState<ContentChange[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();

  const connect = useCallback(() => {
    if (!taskId) return;

    const ws = new WebSocket(createWsUrl(taskId));
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
    };

    ws.onclose = () => {
      setConnected(false);
      reconnectTimer.current = setTimeout(connect, 5000);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as ProgressEvent;
        setLastMessage(data);

        if (data.type === "insights" && data.insights) {
          setInsights(data.insights);
        }

        if (data.type === "content_changed") {
          setChanges((prev) => [
            {
              id: Date.now(),
              task_id: taskId || "",
              url: data.url || "",
              old_content_hash: null,
              new_content_hash: "",
              change_summary: data.change_summary || null,
              detected_at: data.detected_at || new Date().toISOString(),
            },
            ...prev,
          ]);
        }
      } catch {
        // ignore
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [taskId]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  return { lastMessage, connected, insights, changes };
}
