"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import { API_BASE, api } from "@/lib/api-client";
import type { SSEEvent } from "@/types/api";

type SSECallback = (event: SSEEvent) => void;

// Exponential backoff: 1s, 2s, 4s, 8s, 16s, capped at 30s
const _backoffMs = (attempt: number) =>
  Math.min(1000 * Math.pow(2, attempt), 30_000);

export function useSSE(onEvent: SSECallback) {
  const [connected, setConnected] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);
  const callbackRef = useRef(onEvent);
  const retryAttemptRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    callbackRef.current = onEvent;
  }, [onEvent]);

  const connect = useCallback(() => {
    // Cancel any pending retry timer
    if (retryTimerRef.current !== null) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
    // Close existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }
    let cancelled = false;

    const openConnection = async () => {
      const apiKey =
        typeof window !== "undefined"
          ? localStorage.getItem("bioteam_api_key")
          : null;

      let url = `${API_BASE}/api/v1/sse`;
      if (apiKey) {
        try {
          const streamToken = await api.post<{ token: string }>("/api/v1/auth/stream-token", {
            path: "/api/v1/sse",
          });
          url += `?token=${encodeURIComponent(streamToken.token)}`;
        } catch {
          // Backward-compatible fallback: use raw API key
          url += `?token=${encodeURIComponent(apiKey)}`;
        }
      }

      if (cancelled) return;
      const es = new EventSource(url);
      eventSourceRef.current = es;

      es.onopen = () => {
        setConnected(true);
        retryAttemptRef.current = 0; // reset backoff on successful connection
      };

      es.onerror = () => {
        setConnected(false);
        // Close the stale connection to prevent EventSource from auto-reconnecting
        // with the old (possibly expired) token URL.
        es.close();
        if (eventSourceRef.current === es) {
          eventSourceRef.current = null;
        }

        if (!cancelled) {
          // Reconnect with a fresh token after backoff
          const delay = _backoffMs(retryAttemptRef.current);
          retryAttemptRef.current += 1;
          retryTimerRef.current = setTimeout(() => {
            if (!cancelled) void openConnection();
          }, delay);
        }
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
    };

    void openConnection();

    return () => {
      cancelled = true;
      if (retryTimerRef.current !== null) {
        clearTimeout(retryTimerRef.current);
        retryTimerRef.current = null;
      }
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
      setConnected(false);
    };
  }, []);

  useEffect(() => {
    return connect();
  }, [connect]);

  const disconnect = useCallback(() => {
    if (retryTimerRef.current !== null) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    setConnected(false);
  }, []);

  return { connected, disconnect, reconnect: connect };
}
