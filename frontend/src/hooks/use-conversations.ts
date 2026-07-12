"use client";

import { useState, useCallback } from "react";
import { api } from "@/lib/api-client";
import type { ConversationSummary, ConversationDetail } from "@/types/api";

export function useConversations() {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<ConversationSummary[]>("/api/v1/conversations?limit=50");
      setConversations(data);
    } catch {
      // Silently fail — sidebar just stays empty
    } finally {
      setLoading(false);
    }
  }, []);

  const loadConversation = useCallback(async (id: string) => {
    return api.get<ConversationDetail>(`/api/v1/conversations/${id}`);
  }, []);

  const renameConversation = useCallback(async (id: string, title: string) => {
    const updated = await api.patch<ConversationSummary>(
      `/api/v1/conversations/${id}`,
      { title },
    );
    setConversations((prev) =>
      prev.map((c) => (c.id === id ? updated : c)),
    );
    return updated;
  }, []);

  const deleteConversation = useCallback(async (id: string) => {
    await api.delete(`/api/v1/conversations/${id}`);
    setConversations((prev) => prev.filter((c) => c.id !== id));
  }, []);

  return {
    conversations,
    loading,
    refresh,
    loadConversation,
    renameConversation,
    deleteConversation,
  };
}
