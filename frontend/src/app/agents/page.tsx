"use client";

import { useState } from "react";
import { Separator } from "@/components/ui/separator";
import { AgentCharacterCard } from "@/components/agents/agent-character-card";
import { AgentChatSheet } from "@/components/agents/agent-chat-sheet";
import { useAgents } from "@/hooks/use-agents";
import { AGENT_TIER_GROUPS } from "@/lib/agent-characters";
import type { AgentListItem } from "@/types/api";

export default function AgentsPage() {
  const { agents, loading, error } = useAgents();
  const [activeChatAgentId, setActiveChatAgentId] = useState<string | null>(null);

  // Build lookup map for quick access
  const agentMap = new Map<string, AgentListItem>(agents.map((a) => [a.id, a]));

  return (
    <div className="space-y-8">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Research Team</h1>
        <p className="text-sm text-muted-foreground mt-1">
          {agents.length > 0
            ? `${agents.length} agents · Click any agent to start a conversation`
            : "Initializing agents…"}
        </p>
      </div>

      {/* Error state */}
      {error && (
        <div className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
          Failed to load agents. Make sure the backend is running.
        </div>
      )}

      {/* Loading skeleton */}
      {loading && agents.length === 0 && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
          {Array.from({ length: 10 }).map((_, i) => (
            <div
              key={i}
              className="h-[220px] animate-pulse rounded-xl border border-border bg-accent/30"
            />
          ))}
        </div>
      )}

      {/* Tier-grouped roster */}
      {agents.length > 0 && (
        <div className="space-y-8">
          {AGENT_TIER_GROUPS.map((group) => {
            // Only show groups where at least one agent is registered
            const groupAgents = group.agentIds
              .map((id) => agentMap.get(id))
              .filter((a): a is AgentListItem => a !== undefined);

            if (groupAgents.length === 0) return null;

            return (
              <section key={group.label} aria-labelledby={`group-${group.label}`}>
                <div className="mb-3 flex items-center gap-3">
                  <h2
                    id={`group-${group.label}`}
                    className="text-xs font-semibold uppercase tracking-wider text-muted-foreground"
                  >
                    {group.label}
                  </h2>
                  <Separator className="flex-1" />
                  <span className="text-xs text-muted-foreground/60">
                    {groupAgents.length}
                  </span>
                </div>

                <div
                  role="group"
                  aria-label={group.label}
                  className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(158px,1fr))]"
                >
                  {groupAgents.map((agent) => (
                    <AgentCharacterCard
                      key={agent.id}
                      agent={agent}
                      onSelect={setActiveChatAgentId}
                    />
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      )}

      {/* Chat sheet — key resets message history when switching agents */}
      <AgentChatSheet
        key={activeChatAgentId ?? "none"}
        agentId={activeChatAgentId}
        onClose={() => setActiveChatAgentId(null)}
      />
    </div>
  );
}
