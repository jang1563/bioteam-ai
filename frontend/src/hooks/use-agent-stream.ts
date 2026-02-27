"use client";

/**
 * Per-agent streaming hook.
 *
 * Wraps GET /api/v1/direct-query/stream with a fixed `target_agent` parameter,
 * bypassing Research Director classification and routing the query directly to
 * the specified agent with Knowledge Manager memory context.
 *
 * `execute()` returns a Promise that resolves with the final text and sources
 * when streaming completes, so callers can setState from an async handler
 * (not from a useEffect) to satisfy react-hooks/set-state-in-effect rules.
 */

import { useState, useCallback, useRef } from "react";
import { API_BASE, api } from "@/lib/api-client";
import type { StreamStatus, StreamDoneData } from "@/types/api";

export interface AgentStreamSource {
  title?: string;
  doi?: string;
  year?: number;
  source_type?: string;
  content_snippet?: string;
}

export interface AgentStreamResult {
  text: string;
  sources: AgentStreamSource[];
  metadata: StreamDoneData | null;
}

export interface UseAgentStreamReturn {
  status: StreamStatus;
  streamedText: string;
  sources: AgentStreamSource[];
  error: string | null;
  execute: (query: string, conversationId?: string | null) => Promise<AgentStreamResult>;
  reset: () => void;
}

export function useAgentStream(agentId: string | null): UseAgentStreamReturn {
  const [status, setStatus] = useState<StreamStatus>("idle");
  const [streamedText, setStreamedText] = useState("");
  const [sources, setSources] = useState<AgentStreamSource[]>([]);
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  const reset = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
    setStatus("idle");
    setStreamedText("");
    setSources([]);
    setError(null);
  }, []);

  const execute = useCallback(
    (query: string, conversationId?: string | null): Promise<AgentStreamResult> => {
      return new Promise(async (resolve, reject) => {
        if (!agentId) {
          reject(new Error("No agent selected"));
          return;
        }

        // Clean up any previous connection
        esRef.current?.close();
        setStatus("classifying");
        setStreamedText("");
        setSources([]);
        setError(null);

        const apiKey =
          typeof window !== "undefined"
            ? localStorage.getItem("bioteam_api_key")
            : null;

        let url =
          `${API_BASE}/api/v1/direct-query/stream` +
          `?query=${encodeURIComponent(query)}` +
          `&target_agent=${encodeURIComponent(agentId)}`;

        if (conversationId) {
          url += `&conversation_id=${encodeURIComponent(conversationId)}`;
        }

        if (apiKey) {
          try {
            const streamToken = await api.post<{ token: string }>(
              "/api/v1/auth/stream-token",
              { path: "/api/v1/direct-query/stream" },
            );
            url += `&token=${encodeURIComponent(streamToken.token)}`;
          } catch {
            // Fallback for dev environments without stream-token endpoint
            url += `&token=${encodeURIComponent(apiKey)}`;
          }
        }

        // Accumulate text in a ref so the done handler can read the full string
        const textBuffer: string[] = [];

        const es = new EventSource(url);
        esRef.current = es;

        // Classification event — emitted immediately (skips RD routing)
        es.addEventListener("classification", () => {
          setStatus("retrieving");
        });

        // Memory event — Knowledge Manager retrieved context
        es.addEventListener("memory", (e: MessageEvent) => {
          const data = JSON.parse(e.data);
          setSources(data.sources ?? []);
          setStatus("streaming");
        });

        // Token events — streaming answer chunks
        es.addEventListener("token", (e: MessageEvent) => {
          const data = JSON.parse(e.data);
          const chunk = data.text ?? "";
          textBuffer.push(chunk);
          setStreamedText((prev) => prev + chunk);
          setStatus("streaming");
        });

        // Done event — resolve the promise with final result
        es.addEventListener("done", (e: MessageEvent) => {
          const data = JSON.parse(e.data) as StreamDoneData;
          const finalSources = (data.sources ?? []) as AgentStreamSource[];
          const fullText = textBuffer.join("");

          if (finalSources.length > 0) {
            setSources(finalSources);
          }
          setStatus("done");
          es.close();
          esRef.current = null;

          resolve({ text: fullText, sources: finalSources, metadata: data });
        });

        // Named error event from server
        es.addEventListener("error", (e: MessageEvent) => {
          let msg = "Stream error";
          if (e.data) {
            try {
              msg = JSON.parse(e.data).detail ?? msg;
            } catch {
              msg = "Connection lost";
            }
          }
          setError(msg);
          setStatus("error");
          es.close();
          esRef.current = null;
          reject(new Error(msg));
        });

        // Native EventSource connection error
        es.onerror = () => {
          setStatus((prev) => {
            if (prev === "done" || prev === "error") return prev;
            const msg = "Connection to server lost";
            setError(msg);
            reject(new Error(msg));
            es.close();
            esRef.current = null;
            return "error";
          });
        };
      });
    },
    [agentId],
  );

  return { status, streamedText, sources, error, execute, reset };
}
