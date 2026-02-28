"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api-client";
import type {
  CreateTopicRequest,
  DigestEntry,
  DigestReport,
  DigestSource,
  DigestStats,
  SchedulerStatus,
  TopicProfile,
  UpdateTopicRequest,
} from "@/types/api";

// === Topics Hook ===

export function useTopics() {
  const [topics, setTopics] = useState<TopicProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.get<TopicProfile[]>("/api/v1/digest/topics");
      setTopics(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch topics");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const create = useCallback(
    async (req: CreateTopicRequest) => {
      const result = await api.post<TopicProfile>(
        "/api/v1/digest/topics",
        req,
      );
      await refresh();
      return result;
    },
    [refresh],
  );

  const update = useCallback(
    async (id: string, req: UpdateTopicRequest) => {
      const result = await api.put<TopicProfile>(
        `/api/v1/digest/topics/${id}`,
        req,
      );
      await refresh();
      return result;
    },
    [refresh],
  );

  const remove = useCallback(
    async (id: string) => {
      await api.delete(`/api/v1/digest/topics/${id}`);
      await refresh();
    },
    [refresh],
  );

  return { topics, loading, error, refresh, create, update, remove };
}

// === Digest Entries Hook ===

export function useDigestEntries(
  topicId?: string,
  source?: DigestSource,
  days: number = 7,
  sortBy: "relevance" | "date" = "relevance",
) {
  const [entries, setEntries] = useState<DigestEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (topicId) params.set("topic_id", topicId);
      if (source) params.set("source", source);
      params.set("days", String(days));
      params.set("limit", "100");
      params.set("sort_by", sortBy);

      const data = await api.get<DigestEntry[]>(
        `/api/v1/digest/entries?${params}`,
      );
      setEntries(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch entries");
    } finally {
      setLoading(false);
    }
  }, [topicId, source, days, sortBy]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { entries, loading, error, refresh };
}

// === Digest Reports Hook ===

export function useDigestReports(topicId?: string) {
  const [reports, setReports] = useState<DigestReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      const params = topicId ? `?topic_id=${topicId}` : "";
      const data = await api.get<DigestReport[]>(
        `/api/v1/digest/reports${params}`,
      );
      setReports(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch reports");
    } finally {
      setLoading(false);
    }
  }, [topicId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { reports, loading, error, refresh };
}

// === Manual Trigger Hook ===

export function useRunDigest() {
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async (topicId: string) => {
    try {
      setRunning(true);
      setError(null);
      const report = await api.post<DigestReport>(
        `/api/v1/digest/topics/${topicId}/run`,
        {},
      );
      return report;
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to run digest";
      setError(msg);
      throw e;
    } finally {
      setRunning(false);
    }
  }, []);

  return { run, running, error };
}

// === Scheduler Status Hook ===

export function useSchedulerStatus() {
  const [status, setStatus] = useState<SchedulerStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.get<SchedulerStatus>("/api/v1/digest/scheduler/status");
      setStatus(data);
    } catch {
      // Non-critical — scheduler status is informational only
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    // Poll every 60 seconds to keep next-run countdown fresh
    const id = setInterval(refresh, 60_000);
    return () => clearInterval(id);
  }, [refresh]);

  return { status, loading, refresh };
}

// === Stats Hook ===

export function useDigestStats() {
  const [stats, setStats] = useState<DigestStats | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.get<DigestStats>("/api/v1/digest/stats");
      setStats(data);
    } catch {
      // Stats failure is non-critical
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { stats, loading, refresh };
}
