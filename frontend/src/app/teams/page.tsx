"use client";

import { useMemo } from "react";
import {
  Brain,
  FlaskConical,
  ShieldCheck,
  Cog,
  Activity,
  DollarSign,
  PhoneCall,
  AlertTriangle,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useAgents } from "@/hooks/use-agents";
import { useAppStore } from "@/stores/app-store";
import { AgentDetailSheet } from "@/components/dashboard/agent-detail-sheet";
import type { AgentListItem, AgentTier } from "@/types/api";

// ─── Tier metadata ───────────────────────────────────────────────────────────

const TIER_META: Record<
  AgentTier,
  { label: string; description: string; icon: React.ElementType; color: string }
> = {
  strategic: {
    label: "Strategic Layer",
    description: "Research Director, Project Manager, Knowledge Manager",
    icon: Brain,
    color: "text-violet-400",
  },
  domain_expert: {
    label: "Domain Experts",
    description: "10 biology specialists across genomics, transcriptomics, proteomics & more",
    icon: FlaskConical,
    color: "text-blue-400",
  },
  qa: {
    label: "QA Tier",
    description: "Structurally independent — report to Director, not to teams",
    icon: ShieldCheck,
    color: "text-emerald-400",
  },
  engine: {
    label: "Hybrid Engines",
    description: "Code + LLM engines (Ambiguity, Negative Results)",
    icon: Cog,
    color: "text-amber-400",
  },
};

const TIER_ORDER: AgentTier[] = ["strategic", "domain_expert", "qa", "engine"];

// ─── State badge ─────────────────────────────────────────────────────────────

function StateDot({ state }: { state: string }) {
  const cls =
    state === "busy"
      ? "bg-amber-400 animate-pulse"
      : state === "idle"
        ? "bg-emerald-400"
        : state === "unavailable"
          ? "bg-red-400"
          : "bg-muted-foreground";
  return <span className={`inline-block h-2 w-2 rounded-full ${cls}`} />;
}

// ─── Single agent card ───────────────────────────────────────────────────────

function AgentCard({ agent }: { agent: AgentListItem }) {
  const setSelected = useAppStore((s) => s.setSelectedAgentId);

  return (
    <button
      onClick={() => setSelected(agent.id)}
      className="group flex flex-col gap-2 rounded-lg border border-border bg-card p-3 text-left transition-all hover:border-primary/40 hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <StateDot state={agent.state} />
          <span className="truncate text-sm font-medium">{agent.name}</span>
        </div>
        {agent.consecutive_failures > 0 && (
          <Tooltip delayDuration={200}>
            <TooltipTrigger asChild>
              <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-destructive" />
            </TooltipTrigger>
            <TooltipContent side="top">
              {agent.consecutive_failures} consecutive failures
            </TooltipContent>
          </Tooltip>
        )}
      </div>

      <div className="flex items-center gap-1.5 flex-wrap">
        <Badge variant="outline" className="text-[10px] py-0 px-1.5">
          {agent.model_tier}
        </Badge>
        <Badge variant="outline" className="text-[10px] py-0 px-1.5 capitalize">
          {agent.criticality}
        </Badge>
      </div>

      <div className="grid grid-cols-2 gap-1 text-[11px] text-muted-foreground">
        <span className="flex items-center gap-1">
          <PhoneCall className="h-3 w-3" />
          {agent.total_calls.toLocaleString()} calls
        </span>
        <span className="flex items-center gap-1">
          <DollarSign className="h-3 w-3" />
          ${agent.total_cost.toFixed(3)}
        </span>
      </div>
    </button>
  );
}

// ─── Tier section ─────────────────────────────────────────────────────────────

function TierSection({ tier, agents }: { tier: AgentTier; agents: AgentListItem[] }) {
  const meta = TIER_META[tier];
  const Icon = meta.icon;
  const busy = agents.filter((a) => a.state === "busy").length;
  const totalCost = agents.reduce((sum, a) => sum + a.total_cost, 0);
  const totalCalls = agents.reduce((sum, a) => sum + a.total_calls, 0);

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Icon className={`h-4 w-4 ${meta.color}`} />
            <CardTitle className="text-sm font-semibold">{meta.label}</CardTitle>
            <Badge variant="secondary" className="text-xs">
              {agents.length}
            </Badge>
          </div>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            {busy > 0 && (
              <span className="flex items-center gap-1 text-amber-400">
                <Activity className="h-3 w-3" />
                {busy} active
              </span>
            )}
            <span className="flex items-center gap-1">
              <PhoneCall className="h-3 w-3" />
              {totalCalls.toLocaleString()}
            </span>
            <span className="flex items-center gap-1">
              <DollarSign className="h-3 w-3" />${totalCost.toFixed(2)}
            </span>
          </div>
        </div>
        <p className="text-[11px] text-muted-foreground">{meta.description}</p>
      </CardHeader>
      <CardContent>
        <div className="grid gap-2 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4">
          {agents.map((agent) => (
            <AgentCard key={agent.id} agent={agent} />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function TeamsPage() {
  const { agents, loading, error } = useAgents();
  const grouped = useMemo(() => {
    const map: Record<AgentTier, AgentListItem[]> = {
      strategic: [],
      domain_expert: [],
      qa: [],
      engine: [],
    };
    for (const agent of agents) {
      (map[agent.tier] ?? map.domain_expert).push(agent);
    }
    return map;
  }, [agents]);

  const totals = useMemo(
    () => ({
      agents: agents.length,
      busy: agents.filter((a) => a.state === "busy").length,
      cost: agents.reduce((s, a) => s + a.total_cost, 0),
      calls: agents.reduce((s, a) => s + a.total_calls, 0),
    }),
    [agents],
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Research Teams</h1>
          <p className="text-sm text-muted-foreground">
            {totals.agents} agents across 4 tiers
          </p>
        </div>
        <div className="flex items-center gap-4 text-sm text-muted-foreground">
          {totals.busy > 0 && (
            <span className="flex items-center gap-1.5 text-amber-400 font-medium">
              <Activity className="h-4 w-4" />
              {totals.busy} active
            </span>
          )}
          <span className="flex items-center gap-1.5">
            <PhoneCall className="h-4 w-4" />
            {totals.calls.toLocaleString()} total calls
          </span>
          <span className="flex items-center gap-1.5">
            <DollarSign className="h-4 w-4" />${totals.cost.toFixed(2)} total
          </span>
        </div>
      </div>

      {/* Error */}
      {error && (
        <Card className="border-destructive/50 bg-destructive/10">
          <CardContent className="pt-4 text-sm text-destructive">{error}</CardContent>
        </Card>
      )}

      {/* Loading */}
      {loading && (
        <div className="space-y-4">
          {[...Array(3)].map((_, i) => (
            <Card key={i}>
              <CardHeader className="pb-3">
                <Skeleton className="h-5 w-48" />
              </CardHeader>
              <CardContent>
                <div className="grid gap-2 sm:grid-cols-3">
                  {[...Array(3)].map((_, j) => (
                    <Skeleton key={j} className="h-20" />
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Tier sections */}
      {!loading &&
        TIER_ORDER.filter((t) => grouped[t].length > 0).map((tier) => (
          <TierSection key={tier} tier={tier} agents={grouped[tier]} />
        ))}

      {/* Agent detail sheet — reads selectedAgentId from store */}
      <AgentDetailSheet />
    </div>
  );
}
