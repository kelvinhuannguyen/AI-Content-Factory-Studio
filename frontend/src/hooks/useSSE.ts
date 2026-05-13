import { useEffect, useRef, useCallback } from "react";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export type SSEEvent = {
  type: string;
  task_id?: string;
  task_type?: string;
  status?: string;
  progress?: number;
  result_url?: string;
  error?: string;
  message?: string;
};

type SSEHandler = (event: SSEEvent) => void;

export function useSSE(projectId: string | null, onEvent: SSEHandler) {
  const esRef = useRef<EventSource | null>(null);
  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;

  const connect = useCallback(() => {
    if (!projectId) return;
    esRef.current?.close();

    const es = new EventSource(`${BASE}/generation/${projectId}/stream`);
    esRef.current = es;

    es.onmessage = (e) => {
      try {
        const data: SSEEvent = JSON.parse(e.data);
        handlerRef.current(data);
      } catch {
        // ignore malformed events
      }
    };

    es.onerror = () => {
      // auto-reconnect after 3s on error
      es.close();
      setTimeout(connect, 3000);
    };
  }, [projectId]);

  useEffect(() => {
    connect();
    return () => esRef.current?.close();
  }, [connect]);

  const disconnect = useCallback(() => esRef.current?.close(), []);
  return { disconnect };
}
