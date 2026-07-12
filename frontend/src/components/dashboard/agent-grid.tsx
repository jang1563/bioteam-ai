"use client";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { AgentListItem } from "@/types/api";
import { useAppStore } from "@/stores/app-store";

const tierColors: Record<string, string> = {
  strategic: "text-purple-400",
  domain_expert: "text-blue-400",
  qa: "text-amber-400",
  engine: "text-emerald-400",
};

const stateColors: Record<string, string> = {
  idle: "bg-muted-foreground/40",
  busy: "bg-emerald-500 animate-pulse",
  unavailable: "bg-destructive",
  unknown: "bg-muted-foreground/20",
};

interface AgentGridProps {
  agents: AgentListItem[];
}

export function AgentGrid({ agents }: AgentGridProps) {
  const setSelectedAgentId = useAppStore((s) => s.setSelectedAgentId);

  if (agents.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
        No agents registered. Start the backend to initialize agents.
      </div>
    );
  }

  return (
    <div
      role="group"
      aria-label="Agent grid"
      className="grid grid-cols-3 gap-2 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8"
    >
      {agents.map((agent) => (
        <Tooltip key={agent.id} delayDuration={200}>
          <TooltipTrigger asChild>
            <button
              onClick={() => setSelectedAgentId(agent.id)}
              aria-label={`${agent.name}, status: ${agent.state}, tier: ${agent.model_tier}`}
              className={cn(
                "group relative flex flex-col items-center gap-1.5 rounded-lg border border-border p-3 transition-all hover:border-primary/40 hover:bg-accent",
              )}
            >
              {/* Status dot */}
              <div
                aria-hidden="true"
                className={cn(
                  "h-3 w-3 rounded-full",
                  stateColors[agent.state] ?? stateColors.unknown,
                )}
              />
              {/* Name */}
              <span className="text-[10px] leading-tight text-muted-foreground text-center line-clamp-2">
                {agent.name}
              </span>
              {/* Tier indicator */}
              <span
                className={cn(
                  "text-[9px] font-medium uppercase",
                  tierColors[agent.tier] ?? "text-muted-foreground",
                )}
              >
                {agent.model_tier}
              </span>
            </button>
          </TooltipTrigger>
          <TooltipContent side="bottom" className="text-xs">
            <div className="space-y-0.5">
              <p className="font-medium">{agent.name}</p>
              <p>Status: {agent.state}</p>
              <p>Calls: {agent.total_calls} | Cost: ${agent.total_cost.toFixed(3)}</p>
              {agent.consecutive_failures > 0 && (
                <p className="text-destructive">Failures: {agent.consecutive_failures}</p>
              )}
            </div>
          </TooltipContent>
        </Tooltip>
      ))}
    </div>
  );
}
