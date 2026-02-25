"use client";

import { useState, useCallback, useRef } from "react";
import { API_BASE } from "@/lib/api-client";
import type { StreamStatus, StreamClassification, StreamDoneData } from "@/types/api";

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

  const execute = useCallback((query: string, conversationId?: string | null) => {
    // Clean up previous connection
    esRef.current?.close();
    setStatus("classifying");
    setClassification(null);
    setStreamedText("");
    setMetadata(null);
    setSources([]);
    setError(null);

    const token = typeof window !== "undefined"
      ? localStorage.getItem("bioteam_api_key")
      : null;

    let url = `${API_BASE}/api/v1/direct-query/stream?query=${encodeURIComponent(query)}`;
    if (conversationId) {
      url += `&conversation_id=${encodeURIComponent(conversationId)}`;
    }
    if (token) {
      url += `&token=${encodeURIComponent(token)}`;
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
      if (status !== "done" && status !== "error") {
        setError("Connection to server lost");
        setStatus("error");
        es.close();
        esRef.current = null;
      }
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, []);

  return { status, classification, streamedText, metadata, sources, error, execute, reset };
}
