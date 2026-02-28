"use client";

import { useState, useEffect, useCallback } from "react";
import {
  ShieldCheck,
  Zap,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  RefreshCw,
  GitMerge,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { useAgents } from "@/hooks/use-agents";
import { api } from "@/lib/api-client";
import type { AgentListItem, ContradictionEntry } from "@/types/api";

// ─── Contradiction type labels ────────────────────────────────────────────────

const CONTRADICTION_LABELS: Record<string, string> = {
  conditional_truth: "Conditional Truth",
  technical_artifact: "Technical Artifact",
  interpretive_framing: "Interpretive Framing",
  statistical_noise: "Statistical Noise",
  temporal_dynamics: "Temporal Dynamics",
  unknown: "Unknown",
};

const CONTRADICTION_COLORS: Record<string, string> = {
  conditional_truth: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  technical_artifact: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  interpretive_framing: "bg-violet-500/15 text-violet-400 border-violet-500/30",
  statistical_noise: "bg-red-500/15 text-red-400 border-red-500/30",
  temporal_dynamics: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  unknown: "bg-muted text-muted-foreground",
};

// ─── Hooks ────────────────────────────────────────────────────────────────────

function useContradictions() {
  const [contradictions, setContradictions] = useState<ContradictionEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<{ contradictions: ContradictionEntry[]; total: number }>(
        "/api/v1/contradictions",
      );
      setContradictions(data.contradictions ?? []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch contradictions");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { contradictions, loading, error, refresh };
}

// ─── QA Agent card ────────────────────────────────────────────────────────────

function QAAgentCard({ agent }: { agent: AgentListItem }) {
  const healthy = agent.consecutive_failures === 0 && agent.state !== "unavailable";
  return (
    <Card className={healthy ? "" : "border-destructive/40"}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-sm">{agent.name}</CardTitle>
          {healthy ? (
            <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
          ) : (
            <XCircle className="h-4 w-4 text-destructive shrink-0" />
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        <div className="flex gap-1.5 flex-wrap">
          <Badge variant="outline" className="text-[10px]">
            {agent.model_tier}
          </Badge>
          <Badge
            variant="outline"
            className={`text-[10px] ${agent.state === "busy" ? "text-amber-400" : ""}`}
          >
            {agent.state}
          </Badge>
        </div>
        <div className="grid grid-cols-2 text-xs text-muted-foreground gap-1">
          <span>{agent.total_calls} reviews</span>
          <span>${agent.total_cost.toFixed(3)}</span>
          {agent.consecutive_failures > 0 && (
            <span className="col-span-2 text-destructive flex items-center gap-1">
              <AlertTriangle className="h-3 w-3" />
              {agent.consecutive_failures} failures
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Contradiction card ───────────────────────────────────────────────────────

function ContradictionCard({ entry }: { entry: ContradictionEntry }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <Card className="transition-all hover:border-border/80">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-3">
          <div className="flex gap-1.5 flex-wrap">
            {entry.types.map((t) => (
              <Badge
                key={t}
                variant="outline"
                className={`text-[10px] ${CONTRADICTION_COLORS[t] ?? CONTRADICTION_COLORS.unknown}`}
              >
                {CONTRADICTION_LABELS[t] ?? t}
              </Badge>
            ))}
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-[11px] shrink-0"
            onClick={() => setExpanded((e) => !e)}
          >
            {expanded ? "Less" : "More"}
          </Button>
        </div>
        <p className="text-sm text-muted-foreground leading-snug">{entry.description}</p>
      </CardHeader>

      {expanded && (
        <CardContent className="space-y-3 pt-0">
          <Separator />
          <div className="grid gap-2 sm:grid-cols-2">
            <div className="rounded bg-muted/30 p-2 text-xs">
              <p className="font-medium mb-1 text-muted-foreground">Claim A</p>
              <p>{entry.claim_a}</p>
              <p className="mt-1 text-muted-foreground truncate">{entry.source_a}</p>
            </div>
            <div className="rounded bg-muted/30 p-2 text-xs">
              <p className="font-medium mb-1 text-muted-foreground">Claim B</p>
              <p>{entry.claim_b}</p>
              <p className="mt-1 text-muted-foreground truncate">{entry.source_b}</p>
            </div>
          </div>
          {entry.resolution_hypothesis && (
            <div className="rounded bg-primary/5 border border-primary/20 p-2 text-xs">
              <p className="font-medium mb-1 text-primary/80">Resolution Hypothesis</p>
              <p className="text-muted-foreground">{entry.resolution_hypothesis}</p>
            </div>
          )}
          <p className="text-[11px] text-muted-foreground">
            Detected {new Date(entry.detected_at).toLocaleDateString()}
            {entry.workflow_id && ` · workflow ${entry.workflow_id.slice(0, 8)}…`}
          </p>
        </CardContent>
      )}
    </Card>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function QualityPage() {
  const { agents, loading: agentsLoading } = useAgents();
  const { contradictions, loading: contradictionsLoading, error, refresh } = useContradictions();

  const qaAgents = agents.filter((a) => a.tier === "qa");
  const healthyQA = qaAgents.filter((a) => a.consecutive_failures === 0 && a.state !== "unavailable");

  // Contradiction type distribution
  const typeCounts = contradictions.reduce<Record<string, number>>((acc, c) => {
    c.types.forEach((t) => {
      acc[t] = (acc[t] ?? 0) + 1;
    });
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Quality Control</h1>
          <p className="text-sm text-muted-foreground">
            QA tier performance · contradiction detection · evidence integrity
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={refresh} className="gap-2">
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh
        </Button>
      </div>

      {/* Summary cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="pb-1">
            <CardTitle className="text-xs text-muted-foreground flex items-center gap-1.5">
              <ShieldCheck className="h-3.5 w-3.5" /> QA Agents
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{healthyQA.length}/{qaAgents.length}</p>
            <p className="text-xs text-muted-foreground">healthy</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1">
            <CardTitle className="text-xs text-muted-foreground flex items-center gap-1.5">
              <GitMerge className="h-3.5 w-3.5" /> Contradictions
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{contradictions.length}</p>
            <p className="text-xs text-muted-foreground">detected</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1">
            <CardTitle className="text-xs text-muted-foreground flex items-center gap-1.5">
              <Zap className="h-3.5 w-3.5" /> QA Reviews
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">
              {qaAgents.reduce((s, a) => s + a.total_calls, 0)}
            </p>
            <p className="text-xs text-muted-foreground">total reviews</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1">
            <CardTitle className="text-xs text-muted-foreground flex items-center gap-1.5">
              <AlertTriangle className="h-3.5 w-3.5" /> Top Type
            </CardTitle>
          </CardHeader>
          <CardContent>
            {Object.keys(typeCounts).length > 0 ? (
              <>
                <p className="text-sm font-bold">
                  {CONTRADICTION_LABELS[
                    Object.entries(typeCounts).sort((a, b) => b[1] - a[1])[0][0]
                  ] ?? "—"}
                </p>
                <p className="text-xs text-muted-foreground">
                  {Object.entries(typeCounts).sort((a, b) => b[1] - a[1])[0][1]} occurrences
                </p>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">No data</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="qa-agents">
        <TabsList>
          <TabsTrigger value="qa-agents">
            QA Agents
            {qaAgents.length > 0 && (
              <Badge variant="secondary" className="ml-1.5 text-[10px]">
                {qaAgents.length}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="contradictions">
            Contradictions
            {contradictions.length > 0 && (
              <Badge variant="secondary" className="ml-1.5 text-[10px]">
                {contradictions.length}
              </Badge>
            )}
          </TabsTrigger>
        </TabsList>

        {/* QA Agents tab */}
        <TabsContent value="qa-agents" className="space-y-4 pt-4">
          {agentsLoading ? (
            <div className="grid gap-3 sm:grid-cols-3">
              {[...Array(3)].map((_, i) => (
                <Skeleton key={i} className="h-28" />
              ))}
            </div>
          ) : qaAgents.length === 0 ? (
            <p className="text-sm text-muted-foreground">No QA agents registered.</p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {qaAgents.map((a) => (
                <QAAgentCard key={a.id} agent={a} />
              ))}
            </div>
          )}
        </TabsContent>

        {/* Contradictions tab */}
        <TabsContent value="contradictions" className="space-y-3 pt-4">
          {error && (
            <Card className="border-destructive/50 bg-destructive/10">
              <CardContent className="pt-4 text-sm text-destructive">{error}</CardContent>
            </Card>
          )}

          {contradictionsLoading ? (
            <div className="space-y-3">
              {[...Array(3)].map((_, i) => (
                <Skeleton key={i} className="h-20" />
              ))}
            </div>
          ) : contradictions.length === 0 ? (
            <Card className="border-dashed">
              <CardContent className="flex flex-col items-center gap-2 py-10 text-center">
                <GitMerge className="h-8 w-8 text-muted-foreground/40" />
                <p className="text-sm text-muted-foreground">No contradictions detected yet.</p>
                <p className="text-xs text-muted-foreground/70">
                  Run a W1 Literature Review or W6 Ambiguity Analysis to detect contradictions.
                </p>
              </CardContent>
            </Card>
          ) : (
            <>
              {/* Type distribution summary */}
              {Object.keys(typeCounts).length > 0 && (
                <div className="flex gap-2 flex-wrap">
                  {Object.entries(typeCounts)
                    .sort((a, b) => b[1] - a[1])
                    .map(([type, count]) => (
                      <Badge
                        key={type}
                        variant="outline"
                        className={`text-xs ${CONTRADICTION_COLORS[type] ?? ""}`}
                      >
                        {CONTRADICTION_LABELS[type] ?? type}: {count}
                      </Badge>
                    ))}
                </div>
              )}
              <div className="space-y-3">
                {contradictions.map((c) => (
                  <ContradictionCard key={c.id} entry={c} />
                ))}
              </div>
            </>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
