"use client";

import { useState, useCallback, useRef } from "react";
import { API_BASE, api } from "@/lib/api-client";
import type { StreamStatus, StreamClassification, StreamDoneData } from "@/types/api";

type ExecuteOptions = {
  onDone?: (data: StreamDoneData) => void;
};

export function useDirectQueryStream() {
  const [status, setStatus] = useState<StreamStatus>("idle");
  const [classification, setClassification] = useState<StreamClassification | null>(null);
  const [streamedText, setStreamedText] = useState("");
  const [metadata, setMetadata] = useState<StreamDoneData | null>(null);
  const [sources, setSources] = useState<Record<string, unknown>[]>([]);
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  const reset = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
    setStatus("idle");
    setClassification(null);
    setStreamedText("");
    setMetadata(null);
    setSources([]);
    setError(null);
  }, []);

  const execute = useCallback(async (query: string, conversationId?: string | null, options: ExecuteOptions = {}) => {
    // Clean up previous connection
    esRef.current?.close();
    setStatus("classifying");
    setClassification(null);
    setStreamedText("");
    setMetadata(null);
    setSources([]);
    setError(null);

    const apiKey = typeof window !== "undefined"
      ? localStorage.getItem("bioteam_api_key")
      : null;

    let url = `${API_BASE}/api/v1/direct-query/stream?query=${encodeURIComponent(query)}`;
    if (conversationId) {
      url += `&conversation_id=${encodeURIComponent(conversationId)}`;
    }
    if (apiKey) {
      try {
        const streamToken = await api.post<{ token: string }>("/api/v1/auth/stream-token", {
          path: "/api/v1/direct-query/stream",
        });
        url += `&token=${encodeURIComponent(streamToken.token)}`;
      } catch {
        // Backward-compatible fallback if stream-token endpoint is unavailable.
        url += `&token=${encodeURIComponent(apiKey)}`;
      }
    }

    const es = new EventSource(url);
    esRef.current = es;

    es.addEventListener("classification", (e: MessageEvent) => {
      const data = JSON.parse(e.data) as StreamClassification;
      setClassification(data);
      if (data.type === "simple_query") {
        setStatus("retrieving");
      }
    });

    es.addEventListener("memory", (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      setSources(data.sources ?? []);
      setStatus("streaming");
    });

    es.addEventListener("token", (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      setStreamedText((prev) => prev + data.text);
      setStatus("streaming");
    });

    es.addEventListener("done", (e: MessageEvent) => {
      const data = JSON.parse(e.data) as StreamDoneData;
      setMetadata(data);
      if (data.sources) {
        setSources(data.sources);
      }
      setStatus("done");
      options.onDone?.(data);
      es.close();
      esRef.current = null;
    });

    es.addEventListener("error", (e: MessageEvent) => {
      if (e.data) {
        try {
          const data = JSON.parse(e.data);
          setError(data.detail ?? "Stream error");
        } catch {
          setError("Connection lost");
        }
      } else {
        setError("Connection lost");
      }
      setStatus("error");
      es.close();
      esRef.current = null;
    });

    // Native EventSource error (connection refused, etc.)
    es.onerror = () => {
      setStatus((prev) => {
        if (prev === "done" || prev === "error") return prev;
        setError("Connection to server lost");
        return "error";
      });
      es.close();
      esRef.current = null;
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, []);

  return { status, classification, streamedText, metadata, sources, error, execute, reset };
}
