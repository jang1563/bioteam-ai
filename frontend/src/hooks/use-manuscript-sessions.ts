"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api-client";
import type {
  ApproveManuscriptStoryScopeRequest,
  CreateManuscriptSessionRequest,
  ManuscriptDefenseBrief,
  ManuscriptDefenseBriefDocx,
  ManuscriptDefenseBriefPrint,
  LinkManuscriptWorkflowRequest,
  ManuscriptSession,
  RunManuscriptReviewerRisksRequest,
  SelectManuscriptFrameRequest,
} from "@/types/api";

export function useManuscriptSessions() {
  const [sessions, setSessions] = useState<ManuscriptSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.get<ManuscriptSession[]>("/api/v1/manuscript/sessions");
      setSessions(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch manuscript sessions");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const create = useCallback(
    async (req: CreateManuscriptSessionRequest) => {
      const result = await api.post<ManuscriptSession>("/api/v1/manuscript/sessions", req);
      await refresh();
      return result;
    },
    [refresh],
  );

  const linkWorkflow = useCallback(
    async (sessionId: string, req: LinkManuscriptWorkflowRequest) => {
      const result = await api.post<ManuscriptSession>(
        `/api/v1/manuscript/sessions/${sessionId}/link-workflow`,
        req,
      );
      await refresh();
      return result;
    },
    [refresh],
  );

  const selectFrame = useCallback(
    async (sessionId: string, req: SelectManuscriptFrameRequest) => {
      const result = await api.post<ManuscriptSession>(
        `/api/v1/manuscript/sessions/${sessionId}/select-frame`,
        req,
      );
      await refresh();
      return result;
    },
    [refresh],
  );

  const refreshSession = useCallback(
    async (sessionId: string) => {
      const result = await api.post<ManuscriptSession>(
        `/api/v1/manuscript/sessions/${sessionId}/refresh`,
      );
      await refresh();
      return result;
    },
    [refresh],
  );

  const runStoryFrames = useCallback(
    async (sessionId: string) => {
      const result = await api.post<ManuscriptSession>(
        `/api/v1/manuscript/sessions/${sessionId}/run-story-frames`,
      );
      await refresh();
      return result;
    },
    [refresh],
  );

  const runSubmissionChecks = useCallback(
    async (sessionId: string) => {
      const result = await api.post<ManuscriptSession>(
        `/api/v1/manuscript/sessions/${sessionId}/run-submission-checks`,
      );
      await refresh();
      return result;
    },
    [refresh],
  );

  const approveStoryScope = useCallback(
    async (sessionId: string, req: ApproveManuscriptStoryScopeRequest) => {
      const result = await api.post<ManuscriptSession>(
        `/api/v1/manuscript/sessions/${sessionId}/approve-story-scope`,
        req,
      );
      await refresh();
      return result;
    },
    [refresh],
  );

  const runReviewerRisks = useCallback(
    async (sessionId: string, req: RunManuscriptReviewerRisksRequest) => {
      const result = await api.post<ManuscriptSession>(
        `/api/v1/manuscript/sessions/${sessionId}/run-reviewer-risks`,
        req,
      );
      await refresh();
      return result;
    },
    [refresh],
  );

  const resumeReviewerRisks = useCallback(
    async (sessionId: string) => {
      const result = await api.post<ManuscriptSession>(
        `/api/v1/manuscript/sessions/${sessionId}/resume-reviewer-risks`,
      );
      await refresh();
      return result;
    },
    [refresh],
  );

  const uploadReviewerPaper = useCallback(
    async (sessionId: string, file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      const result = await api.postForm<ManuscriptSession>(
        `/api/v1/manuscript/sessions/${sessionId}/upload-reviewer-paper`,
        formData,
      );
      await refresh();
      return result;
    },
    [refresh],
  );

  const runFullSubmissionAudit = useCallback(
    async (sessionId: string) => {
      const result = await api.post<ManuscriptSession>(
        `/api/v1/manuscript/sessions/${sessionId}/run-full-submission-audit`,
      );
      await refresh();
      return result;
    },
    [refresh],
  );

  const getDefenseBrief = useCallback(
    async (sessionId: string) => {
      return api.get<ManuscriptDefenseBrief>(
        `/api/v1/manuscript/sessions/${sessionId}/defense-brief`,
      );
    },
    [],
  );

  const getDefenseBriefPrint = useCallback(
    async (sessionId: string) => {
      return api.get<ManuscriptDefenseBriefPrint>(
        `/api/v1/manuscript/sessions/${sessionId}/defense-brief/print`,
      );
    },
    [],
  );

  const getDefenseBriefDocx = useCallback(
    async (sessionId: string) => {
      return api.get<ManuscriptDefenseBriefDocx>(
        `/api/v1/manuscript/sessions/${sessionId}/defense-brief/docx`,
      );
    },
    [],
  );

  return {
    sessions,
    loading,
    error,
    refresh,
    create,
    linkWorkflow,
    selectFrame,
    refreshSession,
    runStoryFrames,
    runSubmissionChecks,
    approveStoryScope,
    runReviewerRisks,
    resumeReviewerRisks,
    uploadReviewerPaper,
    runFullSubmissionAudit,
    getDefenseBrief,
    getDefenseBriefPrint,
    getDefenseBriefDocx,
  };
}
