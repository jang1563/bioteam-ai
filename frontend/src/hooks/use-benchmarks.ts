"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api-client";
import type {
  BenchmarkActiveStatus,
  BenchmarkComparison,
  BenchmarkDatasetInfo,
  BenchmarkTrendPoint,
  W8BenchmarkRun,
  W9BenchmarkResult,
} from "@/types/api";

// ---------------------------------------------------------------------------
// W9 + W8 unified results
// ---------------------------------------------------------------------------

export type UnifiedResult =
  | ({ _type: "w9" } & W9BenchmarkResult)
  | ({ _type: "w8" } & W8BenchmarkRun);

export function useBenchmarkResults(filter?: "all" | "w9" | "w8") {
  const [results, setResults] = useState<UnifiedResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      const merged: UnifiedResult[] = [];

      if (filter !== "w8") {
        const w9 = await api.get<W9BenchmarkResult[]>("/api/v1/benchmarks/results?limit=50");
        for (const r of w9) merged.push({ _type: "w9", ...r });
      }

      if (filter !== "w9") {
        const w8 = await api.get<W8BenchmarkRun[]>("/api/v1/benchmarks/w8/results?limit=50");
        for (const r of w8) merged.push({ _type: "w8", ...r });
      }

      // Sort newest first
      merged.sort((a, b) => {
        const ta = a._type === "w9" ? a.timestamp : a.created_at;
        const tb = b._type === "w9" ? b.timestamp : b.created_at;
        return (tb ?? "").localeCompare(ta ?? "");
      });

      setResults(merged);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch benchmark results");
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { refresh(); }, [refresh]);

  return { results, loading, error, refresh };
}

// ---------------------------------------------------------------------------
// Datasets
// ---------------------------------------------------------------------------

export function useBenchmarkDatasets() {
  const [datasets, setDatasets] = useState<BenchmarkDatasetInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<BenchmarkDatasetInfo[]>("/api/v1/benchmarks/datasets")
      .then((data) => { setDatasets(data); setError(null); })
      .catch((e) => { setDatasets([]); setError(e instanceof Error ? e.message : "Failed to load datasets"); })
      .finally(() => setLoading(false));
  }, []);

  return { datasets, loading, error };
}

// ---------------------------------------------------------------------------
// Trends
// ---------------------------------------------------------------------------

export function useBenchmarkTrends(metric: string, datasetId?: string) {
  const [trends, setTrends] = useState<BenchmarkTrendPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({ metric, last_n: "30" });
      if (datasetId) params.set("dataset_id", datasetId);
      const data = await api.get<BenchmarkTrendPoint[]>(
        `/api/v1/benchmarks/trends?${params}`,
      );
      setTrends(data);
      setError(null);
    } catch (e) {
      setTrends([]);
      setError(e instanceof Error ? e.message : "Failed to load trends");
    } finally {
      setLoading(false);
    }
  }, [metric, datasetId]);

  useEffect(() => { refresh(); }, [refresh]);

  return { trends, loading, error, refresh };
}

// ---------------------------------------------------------------------------
// Compare
// ---------------------------------------------------------------------------

export function useBenchmarkCompare(runA?: string, runB?: string) {
  const [comparison, setComparison] = useState<BenchmarkComparison | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const compare = useCallback(async () => {
    if (!runA || !runB) return;
    try {
      setLoading(true);
      setError(null);
      const params = new URLSearchParams({ a: runA, b: runB });
      const data = await api.get<BenchmarkComparison>(
        `/api/v1/benchmarks/compare?${params}`,
      );
      setComparison(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Comparison failed");
      setComparison(null);
    } finally {
      setLoading(false);
    }
  }, [runA, runB]);

  return { comparison, loading, error, compare };
}

// ---------------------------------------------------------------------------
// Active run status (polls every 10s when a run is active)
// ---------------------------------------------------------------------------

export function useBenchmarkActive() {
  const [status, setStatus] = useState<BenchmarkActiveStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const data = await api.get<BenchmarkActiveStatus>("/api/v1/benchmarks/runs/active");
      setStatus(data);
      return data;
    } catch {
      setStatus(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus().then((data) => {
      // Start polling if a run is active
      if (data && data.status !== "idle") {
        intervalRef.current = setInterval(async () => {
          const updated = await fetchStatus();
          // Stop polling when run completes
          if (!updated || updated.status === "idle" || updated.status === "completed" || updated.status === "failed") {
            if (intervalRef.current) clearInterval(intervalRef.current);
            intervalRef.current = null;
          }
        }, 10_000);
      }
    });

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchStatus]);

  return { status, loading };
}
