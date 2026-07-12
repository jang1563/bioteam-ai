"use client";

import React, { useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  TrendingUp,
  DollarSign,
  Cpu,
  Activity,
  BarChart3,
  Loader2,
} from "lucide-react";
import { api } from "@/lib/api-client";

// ─── API Types ────────────────────────────────────────────────────────────────

interface AnalyticsSummary {
  total_workflows: number;
  completed_workflows: number;
  failed_workflows: number;
  running_workflows: number;
  total_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
  avg_cost_per_workflow: number;
}

interface TemplateStats {
  template: string;
  total: number;
  completed: number;
  failed: number;
  total_cost_usd: number;
}

interface WorkflowBreakdown {
  by_template: TemplateStats[];
  by_state: Record<string, number>;
}

interface DailyCostEntry {
  date: string;
  cost_usd: number;
  workflow_count: number;
}

interface CostByDay {
  days: number;
  entries: DailyCostEntry[];
  total_cost_usd: number;
}

interface AgentStats {
  agent_id: string;
  call_count: number;
  total_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
}

interface AgentsResponse {
  agents: AgentStats[];
  total_agents_used: number;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtCost(v: number): string {
  if (v === 0) return "$0.00";
  if (v < 0.01) return `$${v.toFixed(4)}`;
  return `$${v.toFixed(2)}`;
}

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return String(n);
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function SummaryCard({
  title,
  value,
  sub,
  icon: Icon,
  color,
}: {
  title: string;
  value: string;
  sub?: string;
  icon: React.ElementType;
  color?: string;
}) {
  return (
    <Card>
      <CardContent className="pt-4 pb-4">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs text-muted-foreground">{title}</p>
            <p className={`text-2xl font-bold mt-1 ${color ?? ""}`}>{value}</p>
            {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
          </div>
          <Icon className="h-5 w-5 text-muted-foreground/50" />
        </div>
      </CardContent>
    </Card>
  );
}

// Mini sparkline for daily cost (SVG-based, no library)
function CostSparkline({ entries }: { entries: DailyCostEntry[] }) {
  if (!entries.length) return null;
  const maxCost = Math.max(...entries.map((e) => e.cost_usd), 0.001);
  const W = 400;
  const H = 80;
  const pad = 4;
  const points = entries.map((e, i) => {
    const x = pad + (i / Math.max(entries.length - 1, 1)) * (W - pad * 2);
    const y = H - pad - ((e.cost_usd / maxCost) * (H - pad * 2));
    return `${x},${y}`;
  });

  const polyline = points.join(" ");
  // Fill area
  const fillPoints =
    `${pad},${H - pad} ` +
    polyline +
    ` ${W - pad},${H - pad}`;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full h-20"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <polygon points={fillPoints} fill="hsl(var(--primary)/0.08)" />
      <polyline
        points={polyline}
        fill="none"
        stroke="hsl(var(--primary))"
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {/* Dots for every 5th entry */}
      {entries.map((_e, i) => {
        if (i % 5 !== 0 && i !== entries.length - 1) return null;
        const [x, y] = points[i].split(",").map(Number);
        return (
          <circle key={i} cx={x} cy={y} r="2" fill="hsl(var(--primary))" />
        );
      })}
    </svg>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function AnalyticsPage() {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [breakdown, setBreakdown] = useState<WorkflowBreakdown | null>(null);
  const [costByDay, setCostByDay] = useState<CostByDay | null>(null);
  const [agentsResp, setAgentsResp] = useState<AgentsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError("");
      try {
        const [s, b, c, a] = await Promise.all([
          api.get<AnalyticsSummary>("/api/v1/analytics/summary"),
          api.get<WorkflowBreakdown>("/api/v1/analytics/workflows"),
          api.get<CostByDay>("/api/v1/analytics/cost-by-day?days=30"),
          api.get<AgentsResponse>("/api/v1/analytics/agents"),
        ]);
        setSummary(s);
        setBreakdown(b);
        setCostByDay(c);
        setAgentsResp(a);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load analytics");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 gap-3 text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" />
        <span className="text-sm">Loading analytics…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 text-sm text-destructive">{error}</div>
    );
  }

  const maxTemplateCost = Math.max(
    ...(breakdown?.by_template.map((t) => t.total_cost_usd) ?? [0]),
    0.001,
  );
  const maxAgentCost = Math.max(
    ...(agentsResp?.agents.slice(0, 10).map((a) => a.total_cost_usd) ?? [0]),
    0.001,
  );

  return (
    <div className="flex flex-col gap-6 p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3">
        <BarChart3 className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold">Analytics</h1>
          <p className="text-sm text-muted-foreground">
            Workflow runs, cost, and agent usage across all sessions
          </p>
        </div>
      </div>

      {/* Summary cards */}
      {summary && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <SummaryCard
            title="Total Workflows"
            value={String(summary.total_workflows)}
            sub={`${summary.completed_workflows} completed · ${summary.failed_workflows} failed`}
            icon={Activity}
          />
          <SummaryCard
            title="Total Cost"
            value={fmtCost(summary.total_cost_usd)}
            sub={`avg ${fmtCost(summary.avg_cost_per_workflow)} / workflow`}
            icon={DollarSign}
            color="text-emerald-600"
          />
          <SummaryCard
            title="Input Tokens"
            value={fmtTokens(summary.total_input_tokens)}
            sub="total prompt tokens"
            icon={Cpu}
          />
          <SummaryCard
            title="Output Tokens"
            value={fmtTokens(summary.total_output_tokens)}
            sub="total completion tokens"
            icon={TrendingUp}
          />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Workflow state breakdown */}
        {breakdown && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Workflow States</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {Object.entries(breakdown.by_state)
                .sort(([, a], [, b]) => b - a)
                .map(([state, count]) => {
                  const total = summary?.total_workflows ?? 1;
                  return (
                    <div key={state} className="space-y-1">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-medium">{state}</span>
                        <span className="text-muted-foreground">
                          {count} ({Math.round((count / total) * 100)}%)
                        </span>
                      </div>
                      <Progress value={(count / total) * 100} className="h-1.5" />
                    </div>
                  );
                })}
              {Object.keys(breakdown.by_state).length === 0 && (
                <p className="text-xs text-muted-foreground py-4 text-center">No workflows yet.</p>
              )}
            </CardContent>
          </Card>
        )}

        {/* Cost by day sparkline */}
        {costByDay && (
          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Cost — Last 30 Days</CardTitle>
                <span className="text-xs text-muted-foreground font-mono">
                  {fmtCost(costByDay.total_cost_usd)} total
                </span>
              </div>
            </CardHeader>
            <CardContent>
              <CostSparkline entries={costByDay.entries} />
              {/* X-axis labels: first and last date */}
              <div className="flex justify-between text-[10px] text-muted-foreground mt-1">
                <span>{costByDay.entries[0]?.date ?? ""}</span>
                <span>{costByDay.entries[costByDay.entries.length - 1]?.date ?? ""}</span>
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Template cost breakdown */}
      {breakdown && breakdown.by_template.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Cost by Workflow Template</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {breakdown.by_template
              .sort((a, b) => b.total_cost_usd - a.total_cost_usd)
              .map((t) => (
                <div key={t.template} className="space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-4">
                        {t.template}
                      </Badge>
                      <span className="text-muted-foreground">
                        {t.total} run{t.total !== 1 ? "s" : ""}
                      </span>
                      {t.failed > 0 && (
                        <span className="text-destructive text-[10px]">{t.failed} failed</span>
                      )}
                    </div>
                    <span className="font-mono">{fmtCost(t.total_cost_usd)}</span>
                  </div>
                  <Progress
                    value={(t.total_cost_usd / maxTemplateCost) * 100}
                    className="h-2"
                  />
                </div>
              ))}
          </CardContent>
        </Card>
      )}

      {/* Top agents */}
      {agentsResp && agentsResp.agents.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Agent Usage</CardTitle>
              <span className="text-xs text-muted-foreground">
                {agentsResp.total_agents_used} agents used
              </span>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {agentsResp.agents.slice(0, 10).map((agent) => (
              <div key={agent.agent_id} className="space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
                    <span className="font-medium font-mono text-[11px]">{agent.agent_id}</span>
                    <span className="text-muted-foreground">
                      {agent.call_count} call{agent.call_count !== 1 ? "s" : ""}
                    </span>
                    <span className="text-muted-foreground text-[10px]">
                      {fmtTokens(agent.total_input_tokens + agent.total_output_tokens)} tok
                    </span>
                  </div>
                  <span className="font-mono">{fmtCost(agent.total_cost_usd)}</span>
                </div>
                <Progress
                  value={(agent.total_cost_usd / maxAgentCost) * 100}
                  className="h-1.5"
                />
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {summary && summary.total_workflows === 0 && (
        <Card>
          <CardContent className="py-16 flex flex-col items-center gap-3 text-muted-foreground">
            <BarChart3 className="h-10 w-10 opacity-20" />
            <p className="text-sm">No workflow runs yet.</p>
            <p className="text-xs opacity-70">Run a workflow to see cost and usage analytics.</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
