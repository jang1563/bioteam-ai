"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import { API_BASE } from "@/lib/api-client";
import type { SSEEvent } from "@/types/api";

type SSECallback = (event: SSEEvent) => void;

export function useSSE(onEvent: SSECallback) {
  const [connected, setConnected] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);
  const callbackRef = useRef(onEvent);
  callbackRef.current = onEvent;

  const connect = useCallback(() => {
    // Close existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("bioteam_api_key")
        : null;
    const url = token
      ? `${API_BASE}/api/v1/sse?token=${encodeURIComponent(token)}`
      : `${API_BASE}/api/v1/sse`;

    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.onopen = () => setConnected(true);

    es.onerror = () => {
      setConnected(false);
      // EventSource auto-reconnects
    };

    // Listen for all known event types
    const eventTypes = [
      "workflow.created",
      "workflow.step_started",
      "workflow.step_completed",
      "workflow.completed",
      "workflow.failed",
      "workflow.paused",
      "workflow.resumed",
      "workflow.cancelled",
      "workflow.note_injected",
      "workflow.intervention",
      "agent.status_changed",
      "system.alert",
    ];

    for (const type of eventTypes) {
      es.addEventListener(type, (e: MessageEvent) => {
        try {
          const data: SSEEvent = JSON.parse(e.data);
          callbackRef.current(data);
        } catch {
          // ignore malformed events
        }
      });
    }

    return es;
  }, []);

  useEffect(() => {
    const es = connect();
    return () => {
      es.close();
      setConnected(false);
    };
  }, [connect]);

  const disconnect = useCallback(() => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    setConnected(false);
  }, []);

  return { connected, disconnect, reconnect: connect };
}
