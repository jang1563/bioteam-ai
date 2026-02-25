"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api-client";
import type {
  AuditFinding,
  AuditRun,
  FindingStatus,
  IntegritySeverity,
  IntegrityStats,
  TriggerAuditRequest,
  UpdateFindingRequest,
} from "@/types/api";

interface FindingsFilters {
  severity?: IntegritySeverity;
  category?: string;
  status?: FindingStatus;
  workflow_id?: string;
}

export function useIntegrityFindings(filters?: FindingsFilters) {
  const [findings, setFindings] = useState<AuditFinding[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (filters?.severity) params.set("severity", filters.severity);
      if (filters?.category) params.set("category", filters.category);
      if (filters?.status) params.set("status", filters.status);
      if (filters?.workflow_id) params.set("workflow_id", filters.workflow_id);
      const qs = params.toString();
      const data = await api.get<AuditFinding[]>(
        `/api/v1/integrity/findings${qs ? `?${qs}` : ""}`,
      );
      setFindings(data);
      setError(null);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Failed to fetch integrity findings",
      );
    } finally {
      setLoading(false);
    }
  }, [filters?.severity, filters?.category, filters?.status, filters?.workflow_id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const updateFinding = useCallback(
    async (id: string, req: UpdateFindingRequest) => {
      const result = await api.put<AuditFinding>(
        `/api/v1/integrity/findings/${id}`,
        req,
      );
      await refresh();
      return result;
    },
    [refresh],
  );

  const deleteFinding = useCallback(
    async (id: string) => {
      await api.delete(`/api/v1/integrity/findings/${id}`);
      await refresh();
    },
    [refresh],
  );

  const triggerAudit = useCallback(
    async (req: TriggerAuditRequest) => {
      const result = await api.post<AuditRun>(
        "/api/v1/integrity/audit",
        req,
      );
      await refresh();
      return result;
    },
    [refresh],
  );

  return { findings, loading, error, refresh, updateFinding, deleteFinding, triggerAudit };
}

export function useIntegrityStats() {
  const [stats, setStats] = useState<IntegrityStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<IntegrityStats>("/api/v1/integrity/stats")
      .then(setStats)
      .catch(() => setStats(null))
      .finally(() => setLoading(false));
  }, []);

  return { stats, loading };
}

export function useIntegrityRuns() {
  const [runs, setRuns] = useState<AuditRun[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.get<AuditRun[]>("/api/v1/integrity/runs");
      setRuns(data);
    } catch {
      setRuns([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { runs, loading, refresh };
}
