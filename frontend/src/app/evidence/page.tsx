"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import {
  BarChart3,
  Filter,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Layers,
  Download,
} from "lucide-react";
import { useAppStore } from "@/stores/app-store";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { api } from "@/lib/api-client";
import type { WorkflowStatus, RCMXTScore } from "@/types/api";

// ─── RCMXT axis metadata ──────────────────────────────────────────────────────

const AXES = [
  { key: "R", label: "Reproducibility", color: "bg-blue-400" },
  { key: "C", label: "Condition-specificity", color: "bg-violet-400" },
  { key: "M", label: "Methodological robustness", color: "bg-emerald-400" },
  { key: "X", label: "Cross-omics consistency", color: "bg-amber-400", nullable: true },
  { key: "T", label: "Temporal stability", color: "bg-rose-400" },
] as const;

type AxisKey = "R" | "C" | "M" | "X" | "T";

function scoreColor(v: number | null): string {
  if (v === null) return "text-muted-foreground";
  if (v >= 0.7) return "text-emerald-400";
  if (v >= 0.4) return "text-amber-400";
  return "text-red-400";
}

// ─── RCMXT mini bar ───────────────────────────────────────────────────────────

function RCMXTBar({ score }: { score: RCMXTScore }) {
  return (
    <div className="grid grid-cols-5 gap-1 text-[10px]">
      {AXES.map(({ key, label, color }) => {
        const val = score[key as AxisKey];
        return (
          <div key={key} title={label} className="space-y-0.5">
            <div className="flex justify-between">
              <span className="text-muted-foreground">{key}</span>
              <span className={scoreColor(val)}>
                {val !== null ? val.toFixed(2) : "—"}
              </span>
            </div>
            <Progress
              value={val !== null ? val * 100 : 0}
              className={`h-1 ${val === null ? "opacity-30" : ""}`}
              indicatorClassName={color}
            />
          </div>
        );
      })}
    </div>
  );
}

// ─── Evidence row ─────────────────────────────────────────────────────────────

interface EvidenceRow {
  workflowId: string;
  template: string;
  query: string;
  score: RCMXTScore;
  createdAt?: string;
}

function EvidenceCard({ row, onWorkflowClick }: {
  row: EvidenceRow;
  onWorkflowClick: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const composite = row.score.composite;

  return (
    <Card className="transition-all hover:border-border/80">
      <CardHeader className="pb-2">
        <div className="flex items-start gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <Badge variant="outline" className="text-[10px] shrink-0">
                {row.template}
              </Badge>
              {composite !== null && (
                <span className={`text-xs font-mono font-medium ${scoreColor(composite)}`}>
                  {composite.toFixed(3)}
                </span>
              )}
            </div>
            <p className="text-sm font-medium leading-snug truncate" title={row.score.claim}>
              {row.score.claim}
            </p>
            {row.score.sources.length > 0 && (
              <p className="text-[11px] text-muted-foreground truncate mt-0.5">
                {row.score.sources.slice(0, 2).join(" · ")}
                {row.score.sources.length > 2 && ` +${row.score.sources.length - 2}`}
              </p>
            )}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => onWorkflowClick(row.workflowId)}
              title="Open workflow"
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => setExpanded((e) => !e)}
            >
              {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            </Button>
          </div>
        </div>
      </CardHeader>

      {expanded && (
        <CardContent className="pt-0 space-y-2">
          <RCMXTBar score={row.score} />
          <div className="flex gap-3 text-[11px] text-muted-foreground">
            <span>Scorer v{row.score.scorer_version}</span>
            <span>{row.score.model_version}</span>
            <span className="text-primary/70 hover:underline cursor-pointer truncate"
              onClick={() => onWorkflowClick(row.workflowId)}>
              {row.workflowId.slice(0, 12)}…
            </span>
          </div>
        </CardContent>
      )}
    </Card>
  );
}

// ─── Hooks ────────────────────────────────────────────────────────────────────

function useEvidenceRows() {
  const [rows, setRows] = useState<EvidenceRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const workflows = await api.get<WorkflowStatus[]>("/api/v1/workflows");
      const extracted: EvidenceRow[] = [];
      for (const wf of workflows) {
        for (const score of wf.rcmxt_scores ?? []) {
          extracted.push({
            workflowId: wf.id,
            template: wf.template,
            query: wf.query,
            score,
            createdAt: wf.created_at,
          });
        }
      }
      // Sort by composite score desc (null scores go last)
      extracted.sort((a, b) => {
        const ca = a.score.composite ?? -1;
        const cb = b.score.composite ?? -1;
        return cb - ca;
      });
      setRows(extracted);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load evidence");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { rows, loading, error, refresh };
}

// ─── Aggregate stats ──────────────────────────────────────────────────────────

function AxisStats({ rows }: { rows: EvidenceRow[] }) {
  const stats = useMemo(() => {
    return AXES.map(({ key, label, color }) => {
      const vals = rows
        .map((r) => r.score[key as AxisKey])
        .filter((v): v is number => v !== null);
      const avg = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
      return { key, label, color, avg, n: vals.length };
    });
  }, [rows]);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-1.5">
          <BarChart3 className="h-4 w-4" /> Axis Averages
          <span className="text-xs text-muted-foreground font-normal">
            ({rows.length} scored claims)
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {stats.map(({ key, label, color, avg, n }) => (
            <div key={key} className="flex items-center gap-3">
              <span className="w-4 text-xs text-muted-foreground shrink-0">{key}</span>
              <div className="flex-1">
                <Progress
                  value={avg !== null ? avg * 100 : 0}
                  className="h-2"
                  indicatorClassName={color}
                />
              </div>
              <span className={`text-xs font-mono w-10 text-right ${scoreColor(avg)}`}>
                {avg !== null ? avg.toFixed(2) : "—"}
              </span>
              <span className="text-[10px] text-muted-foreground w-14 text-right">{label}</span>
              <span className="text-[10px] text-muted-foreground w-10 text-right">n={n}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

const SCORE_FILTERS = ["All", "High (≥0.7)", "Medium (0.4–0.7)", "Low (<0.4)"] as const;
type ScoreFilter = (typeof SCORE_FILTERS)[number];

export default function EvidencePage() {
  const { rows, loading, error, refresh } = useEvidenceRows();
  const [scoreFilter, setScoreFilter] = useState<ScoreFilter>("All");
  const [templateFilter, setTemplateFilter] = useState<string>("All");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const templates = useMemo(() => {
    const set = new Set(rows.map((r) => r.template));
    return ["All", ...Array.from(set).sort()];
  }, [rows]);

  const filtered = useMemo(() => {
    return rows.filter((r) => {
      if (templateFilter !== "All" && r.template !== templateFilter) return false;
      const c = r.score.composite;
      if (scoreFilter === "High (≥0.7)") return c !== null && c >= 0.7;
      if (scoreFilter === "Medium (0.4–0.7)") return c !== null && c >= 0.4 && c < 0.7;
      if (scoreFilter === "Low (<0.4)") return c !== null && c < 0.4;
      return true;
    });
  }, [rows, scoreFilter, templateFilter]);

  const dateFiltered = useMemo(() => {
    if (!dateFrom && !dateTo) return filtered;
    return filtered.filter((r) => {
      const ts = r.createdAt ? new Date(r.createdAt).getTime() : 0;
      if (dateFrom && ts < new Date(dateFrom).getTime()) return false;
      if (dateTo && ts > new Date(dateTo + "T23:59:59").getTime()) return false;
      return true;
    });
  }, [filtered, dateFrom, dateTo]);

  const exportCsv = useCallback(() => {
    const header = "workflow_id,template,query,composite,R,C,M,X,T,claim,created_at\n";
    const body = dateFiltered.map((r) => [
      r.workflowId,
      r.template,
      `"${r.query.replace(/"/g, '""')}"`,
      r.score.composite?.toFixed(3) ?? "",
      r.score.R.toFixed(3),
      r.score.C.toFixed(3),
      r.score.M.toFixed(3),
      r.score.X?.toFixed(3) ?? "",
      r.score.T.toFixed(3),
      `"${r.score.claim.replace(/"/g, '""')}"`,
      r.createdAt ?? "",
    ].join(",")).join("\n");
    const blob = new Blob([header + body], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "evidence.csv";
    a.click();
    URL.revokeObjectURL(url);
  }, [dateFiltered]);

  const setSelectedWorkflow = useAppStore((s) => s.setSelectedWorkflowId);
  const handleWorkflowClick = useCallback((id: string) => {
    setSelectedWorkflow(id);
  }, [setSelectedWorkflow]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Evidence Explorer</h1>
          <p className="text-sm text-muted-foreground">
            RCMXT-scored claims from completed workflows
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={refresh} className="gap-2">
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh
        </Button>
      </div>

      {error && (
        <Card className="border-destructive/50 bg-destructive/10">
          <CardContent className="pt-4 text-sm text-destructive">{error}</CardContent>
        </Card>
      )}

      {/* Loading */}
      {loading ? (
        <div className="space-y-3">
          <Skeleton className="h-32" />
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center gap-2 py-12 text-center">
            <Layers className="h-8 w-8 text-muted-foreground/40" />
            <p className="text-sm text-muted-foreground">No scored evidence yet.</p>
            <p className="text-xs text-muted-foreground/70">
              Run a W1 Literature Review or W2 Hypothesis Generation to generate RCMXT scores.
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Axis stats */}
          <AxisStats rows={rows} />

          {/* Filters */}
          <div className="flex items-center gap-3 flex-wrap">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <Select value={scoreFilter} onValueChange={(v) => setScoreFilter(v as ScoreFilter)}>
              <SelectTrigger className="h-8 w-48 text-xs">
                <SelectValue placeholder="Score filter" />
              </SelectTrigger>
              <SelectContent>
                {SCORE_FILTERS.map((f) => (
                  <SelectItem key={f} value={f} className="text-xs">
                    {f}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={templateFilter} onValueChange={setTemplateFilter}>
              <SelectTrigger className="h-8 w-40 text-xs">
                <SelectValue placeholder="Workflow" />
              </SelectTrigger>
              <SelectContent>
                {templates.map((t) => (
                  <SelectItem key={t} value={t} className="text-xs">
                    {t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <label htmlFor="date-from" className="sr-only">From date</label>
            <Input
              id="date-from"
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="h-8 w-[150px] text-xs"
              aria-label="From date"
            />
            <span className="text-xs text-muted-foreground">–</span>
            <label htmlFor="date-to" className="sr-only">To date</label>
            <Input
              id="date-to"
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="h-8 w-[150px] text-xs"
              aria-label="To date"
            />
            <span className="text-xs text-muted-foreground">
              {dateFiltered.length} / {rows.length} claims
            </span>
            <Button size="sm" variant="outline" className="h-8 gap-1.5 text-xs ml-auto" onClick={exportCsv}>
              <Download className="h-3.5 w-3.5" />
              Export CSV
            </Button>
          </div>

          {/* Evidence cards */}
          <div className="space-y-3">
            {dateFiltered.map((row, i) => (
              <EvidenceCard
                key={`${row.workflowId}-${i}`}
                row={row}
                onWorkflowClick={handleWorkflowClick}
              />
            ))}
            {dateFiltered.length === 0 && (
              <p className="text-sm text-center text-muted-foreground py-8">
                No claims match the current filters.
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}
