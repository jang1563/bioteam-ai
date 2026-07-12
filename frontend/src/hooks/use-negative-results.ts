"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api-client";
import type {
  CreateNegativeResultRequest,
  NegativeResult,
  NRSource,
  UpdateNegativeResultRequest,
} from "@/types/api";

export function useNegativeResults(sourceFilter?: NRSource) {
  const [results, setResults] = useState<NegativeResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      const params = sourceFilter ? `?source=${sourceFilter}` : "";
      const data = await api.get<NegativeResult[]>(
        `/api/v1/negative-results${params}`,
      );
      setResults(data);
      setError(null);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Failed to fetch negative results",
      );
    } finally {
      setLoading(false);
    }
  }, [sourceFilter]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const create = useCallback(
    async (req: CreateNegativeResultRequest) => {
      const result = await api.post<NegativeResult>(
        "/api/v1/negative-results",
        req,
      );
      await refresh();
      return result;
    },
    [refresh],
  );

  const update = useCallback(
    async (id: string, req: UpdateNegativeResultRequest) => {
      const result = await api.put<NegativeResult>(
        `/api/v1/negative-results/${id}`,
        req,
      );
      await refresh();
      return result;
    },
    [refresh],
  );

  const remove = useCallback(
    async (id: string) => {
      await api.delete(`/api/v1/negative-results/${id}`);
      await refresh();
    },
    [refresh],
  );

  return { results, loading, error, refresh, create, update, remove };
}
