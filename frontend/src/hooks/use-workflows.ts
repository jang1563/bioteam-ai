"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api-client";
import type {
  CreateWorkflowRequest,
  CreateWorkflowResponse,
  InterveneRequest,
  InterveneResponse,
  WorkflowStatus,
} from "@/types/api";

export function useWorkflows() {
  const [workflows, setWorkflows] = useState<WorkflowStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.get<WorkflowStatus[]>("/api/v1/workflows");
      setWorkflows(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch workflows");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const create = useCallback(async (req: CreateWorkflowRequest) => {
    const result = await api.post<CreateWorkflowResponse>(
      "/api/v1/workflows",
      req,
    );
    await refresh();
    return result;
  }, [refresh]);

  const intervene = useCallback(
    async (workflowId: string, req: InterveneRequest) => {
      const result = await api.post<InterveneResponse>(
        `/api/v1/workflows/${workflowId}/intervene`,
        req,
      );
      await refresh();
      return result;
    },
    [refresh],
  );

  return { workflows, loading, error, refresh, create, intervene };
}

export function useWorkflowDetail(workflowId: string | null) {
  const [workflow, setWorkflow] = useState<WorkflowStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!workflowId) {
      setWorkflow(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        const data = await api.get<WorkflowStatus>(
          `/api/v1/workflows/${workflowId}`,
        );
        if (!cancelled) {
          setWorkflow(data);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setError(
            e instanceof Error ? e.message : "Failed to fetch workflow",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [workflowId]);

  return { workflow, loading, error };
}
