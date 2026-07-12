"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api-client";
import type {
  AgentDetail,
  AgentHistoryResponse,
  AgentListItem,
  AgentQueryRequest,
  AgentQueryResponse,
} from "@/types/api";

export function useAgents() {
  const [agents, setAgents] = useState<AgentListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.get<AgentListItem[]>("/api/v1/agents");
      setAgents(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch agents");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { agents, loading, error, refresh };
}

export function useAgentDetail(agentId: string | null) {
  const [agent, setAgent] = useState<AgentDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!agentId) {
      setAgent(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        const data = await api.get<AgentDetail>(`/api/v1/agents/${agentId}`);
        if (!cancelled) {
          setAgent(data);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to fetch agent");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [agentId]);

  return { agent, loading, error };
}

export function useAgentQuery(agentId: string | null) {
  const [answer, setAnswer] = useState<AgentQueryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const execute = useCallback(
    async (query: string, context?: string) => {
      if (!agentId) return;
      try {
        setLoading(true);
        setError(null);
        const body: AgentQueryRequest = { query, context };
        const data = await api.post<AgentQueryResponse>(
          `/api/v1/agents/${agentId}/query`,
          body,
        );
        setAnswer(data);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Agent query failed");
      } finally {
        setLoading(false);
      }
    },
    [agentId],
  );

  return { answer, loading, error, execute };
}

export function useAgentHistory(agentId: string | null) {
  const [history, setHistory] = useState<AgentHistoryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadHistory = useCallback(
    async (limit = 20, offset = 0) => {
      if (!agentId) {
        setHistory(null);
        return;
      }
      try {
        setLoading(true);
        const data = await api.get<AgentHistoryResponse>(
          `/api/v1/agents/${agentId}/history?limit=${limit}&offset=${offset}`,
        );
        setHistory(data);
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to fetch history");
      } finally {
        setLoading(false);
      }
    },
    [agentId],
  );

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  return { history, loading, error, loadMore: loadHistory };
}
