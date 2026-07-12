"use client";

import { cn } from "@/lib/utils";
import { getAgentCharacter, AGENT_COLOR_CLASSES } from "@/lib/agent-characters";
import type { AgentListItem } from "@/types/api";

interface AgentCharacterCardProps {
  agent: AgentListItem;
  onSelect: (id: string) => void;
}

const STATE_DOT: Record<string, string> = {
  idle: "bg-muted-foreground/40",
  busy: "bg-emerald-500 animate-pulse",
  unavailable: "bg-destructive",
  unknown: "bg-muted-foreground/20",
};

const STATE_LABEL: Record<string, string> = {
  idle: "Idle",
  busy: "Busy",
  unavailable: "Unavailable",
  unknown: "Unknown",
};

const STATE_RING: Record<string, string> = {
  idle: "",
  busy: "ring-2 ring-emerald-500/50 animate-pulse",
  unavailable: "opacity-40 grayscale",
  unknown: "",
};

export function AgentCharacterCard({ agent, onSelect }: AgentCharacterCardProps) {
  const character = getAgentCharacter(agent.id);
  const colors = AGENT_COLOR_CLASSES[character.color];
  const Icon = character.icon;
  const state = agent.state ?? "unknown";
  const isUnavailable = state === "unavailable";

  return (
    <button
      onClick={() => !isUnavailable && onSelect(agent.id)}
      aria-label={`${agent.name} — ${character.tagline}. Status: ${state}`}
      aria-disabled={isUnavailable}
      title={isUnavailable ? `${agent.name} is currently unavailable` : undefined}
      className={cn(
        "group flex flex-col items-center gap-2 rounded-xl border border-border p-4 text-center",
        "transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        !isUnavailable && "hover:border-primary/40 hover:bg-accent hover:shadow-md hover:scale-[1.03]",
        isUnavailable && "opacity-50 cursor-not-allowed",
      )}
    >
      {/* Avatar circle */}
      <div
        className={cn(
          "flex h-16 w-16 shrink-0 items-center justify-center rounded-full",
          "ring-1",
          colors.bg,
          colors.ring,
          STATE_RING[state],
        )}
        aria-hidden="true"
      >
        <Icon className={cn("h-8 w-8", colors.text)} strokeWidth={1.5} />
      </div>

      {/* Name */}
      <p className="text-sm font-semibold leading-tight line-clamp-2">{agent.name}</p>

      {/* Tier / model label */}
      <p className="text-[11px] text-muted-foreground">
        {agent.tier ? agent.tier.replace("_", " ") : ""} · {agent.model_tier}
      </p>

      {/* Tagline */}
      <p className="text-[11px] italic text-muted-foreground line-clamp-2 leading-snug">
        {character.tagline}
      </p>

      {/* Status */}
      <div className="flex items-center gap-1.5 mt-auto">
        <span
          className={cn("h-2 w-2 rounded-full shrink-0", STATE_DOT[state] ?? STATE_DOT.unknown)}
          aria-hidden="true"
        />
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
          {STATE_LABEL[state] ?? state}
        </span>
      </div>
    </button>
  );
}
