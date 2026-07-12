"use client";

import React, { useState, useEffect } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Target,
  Activity,
  FileSearch,
  Dna,
  Loader2,
  TrendingUp,
  TrendingDown,
  ArrowLeftRight,
  LayoutList,
  Database,
  AlertCircle,
  Settings2,
} from "lucide-react";
import {
  useBenchmarkResults,
  useBenchmarkDatasets,
  useBenchmarkTrends,
  useBenchmarkCompare,
  useBenchmarkActive,
  type UnifiedResult,
} from "@/hooks/use-benchmarks";
import type { BenchmarkConfig, BenchmarkTrendPoint } from "@/types/api";
import { api } from "@/lib/api-client";

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtNum(n: number | null | undefined, digits = 3): string {
  if (n == null) return "—";
  return n.toFixed(digits);
}

function fmtDate(iso: string | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function primaryMetric(r: UnifiedResult): { value: number | null; label: string } {
  if (r._type === "w9") {
    return { value: r.bioagent_score, label: "BioAgent" };
  }
  return { value: r.aggregate.overall_concern_recall_avg, label: "Recall" };
}

function runLabel(r: UnifiedResult): string {
  if (r._type === "w9") return r.fair_mode ? `${r.dataset_id} (fair)` : r.dataset_id;
  return r.label;
}

function runTimestamp(r: UnifiedResult): string {
  return r._type === "w9" ? r.timestamp : r.created_at;
}

function gradeBadge(score: number | null) {
  if (score == null) return <Badge variant="outline">—</Badge>;
  if (score >= 0.7) return <Badge className="bg-yellow-500 text-white">GOLD</Badge>;
  if (score >= 0.5) return <Badge className="bg-gray-400 text-white">SILVER</Badge>;
  if (score >= 0.3) return <Badge className="bg-amber-700 text-white">BRONZE</Badge>;
  return <Badge variant="destructive">BELOW</Badge>;
}

// ─── Error Banner ───────────────────────────────────────────────────────────

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-destructive bg-destructive/10 rounded-lg px-4 py-3">
      <AlertCircle className="h-4 w-4 shrink-0" />
      {message}
    </div>
  );
}

// ─── Summary Card ────────────────────────────────────────────────────────────

function SummaryCard({ title, value, sub, icon: Icon }: {
  title: string;
  value: string;
  sub?: string;
  icon: React.ElementType;
}) {
  return (
    <Card>
      <CardContent className="pt-4 pb-4">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs text-muted-foreground">{title}</p>
            <p className="text-2xl font-bold mt-1">{value}</p>
            {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
          </div>
          <Icon className="h-5 w-5 text-muted-foreground/50" />
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Trend Chart (SVG) ──────────────────────────────────────────────────────

function TrendChart({ points }: { points: BenchmarkTrendPoint[] }) {
  if (!points.length) {
    return <p className="text-sm text-muted-foreground py-8 text-center">No trend data available.</p>;
  }
  const values = points.map((p) => p.value);
  const minVal = Math.min(...values);
  const maxVal = Math.max(...values);
  const range = Math.max(maxVal - minVal, 0.001);
  const W = 500;
  const H = 120;
  const pad = 8;
  const coords = points.map((p, i) => {
    const x = pad + (i / Math.max(points.length - 1, 1)) * (W - pad * 2);
    const y = H - pad - (((p.value - minVal) / range) * (H - pad * 2));
    return { x, y, ...p };
  });
  const polyline = coords.map((c) => `${c.x},${c.y}`).join(" ");
  const fill = `${pad},${H - pad} ${polyline} ${W - pad},${H - pad}`;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-32" preserveAspectRatio="none" aria-hidden="true">
      <polygon points={fill} className="fill-primary/10" />
      <polyline
        points={polyline}
        fill="none"
        className="stroke-primary"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {coords.map((c, i) => (
        <circle key={i} cx={c.x} cy={c.y} r="3" className="fill-primary" />
      ))}
    </svg>
  );
}

// ─── Tabs ────────────────────────────────────────────────────────────────────

type TabId = "results" | "datasets" | "trends" | "compare";

const TABS: { id: TabId; label: string; icon: React.ElementType }[] = [
  { id: "results", label: "Results", icon: LayoutList },
  { id: "datasets", label: "Datasets", icon: Database },
  { id: "trends", label: "Trends", icon: TrendingUp },
  { id: "compare", label: "Compare", icon: ArrowLeftRight },
];

// ─── Results Tab ─────────────────────────────────────────────────────────────

function ResultsTab({ results, loading, filter, setFilter }: {
  results: UnifiedResult[];
  loading: boolean;
  filter: "all" | "w9" | "w8";
  setFilter: (f: "all" | "w9" | "w8") => void;
}) {
  const filtered = filter === "all" ? results : results.filter((r) => r._type === filter);

  if (loading) {
    return <div className="flex justify-center py-12"><Loader2 className="animate-spin h-6 w-6" /></div>;
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2" role="group" aria-label="Filter by benchmark type">
        {(["all", "w9", "w8"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            aria-pressed={filter === f}
            className={`px-3 py-1 text-xs rounded-full border transition-colors ${
              filter === f ? "bg-primary text-primary-foreground" : "bg-muted hover:bg-muted/80"
            }`}
          >
            {f === "all" ? "All" : f === "w9" ? "W9 Bioinfo" : "W8 Peer Review"}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <p className="text-sm text-muted-foreground py-8 text-center">No benchmark results yet. Run a benchmark to see results here.</p>
      ) : (
        <div className="border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="text-left px-3 py-2 font-medium">Label</th>
                <th className="text-left px-3 py-2 font-medium">Type</th>
                <th className="text-right px-3 py-2 font-medium">Primary Metric</th>
                <th className="text-right px-3 py-2 font-medium">Grade</th>
                <th className="text-right px-3 py-2 font-medium">Cost</th>
                <th className="text-right px-3 py-2 font-medium">Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => {
                const { value, label } = primaryMetric(r);
                return (
                  <tr key={r.run_id} className="border-t hover:bg-muted/30">
                    <td className="px-3 py-2 font-mono text-xs">{runLabel(r)}</td>
                    <td className="px-3 py-2">
                      <Badge variant="outline" className="text-xs">
                        {r._type === "w9" ? "W9" : "W8"}
                      </Badge>
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      {fmtNum(value)} <span className="text-muted-foreground text-xs">{label}</span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      {r._type === "w9" ? gradeBadge(r.bioagent_score) : gradeBadge(value)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-xs">
                      {r._type === "w9" ? `$${r.total_cost_usd.toFixed(2)}` : "—"}
                    </td>
                    <td className="px-3 py-2 text-right text-xs text-muted-foreground">
                      {fmtDate(runTimestamp(r))}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── Datasets Tab ────────────────────────────────────────────────────────────

function DatasetsTab() {
  const { datasets, loading, error } = useBenchmarkDatasets();

  if (loading) {
    return <div className="flex justify-center py-12"><Loader2 className="animate-spin h-6 w-6" /></div>;
  }

  if (error) {
    return <ErrorBanner message={error} />;
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {datasets.map((ds) => (
        <Card key={ds.id}>
          <CardHeader className="pb-2">
            <div className="flex items-start justify-between">
              <CardTitle className="text-sm font-medium">{ds.name}</CardTitle>
              <div className="flex gap-1">
                {ds.is_query_only && (
                  <Badge variant="secondary" className="text-xs">query-only</Badge>
                )}
                <Badge variant="outline" className="text-xs">{ds.confidence}</Badge>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-xs text-muted-foreground space-y-1">
              <p>Type: <span className="font-medium text-foreground">{ds.data_type}</span></p>
              <p>Benchmark: <span className="font-medium text-foreground">{ds.benchmark_type}</span></p>
              <div className="flex gap-4 mt-2">
                <span><Dna className="inline h-3 w-3 mr-1" />{ds.expected_gene_count} genes</span>
                <span>{ds.expected_pathway_count} pathways</span>
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
      {datasets.length === 0 && (
        <p className="text-sm text-muted-foreground col-span-full text-center py-8">No datasets available.</p>
      )}
    </div>
  );
}

// ─── Trends Tab ──────────────────────────────────────────────────────────────

function TrendsTab() {
  const [metric, setMetric] = useState("bioagent_score");
  const { trends, loading, error } = useBenchmarkTrends(metric);

  const metrics = [
    "bioagent_score", "gene_recall", "gene_precision", "gene_f1",
    "pathway_overlap", "direction_accuracy", "biology_score",
  ];

  return (
    <div className="space-y-4">
      <div className="flex gap-2 flex-wrap" role="group" aria-label="Select metric">
        {metrics.map((m) => (
          <button
            key={m}
            onClick={() => setMetric(m)}
            aria-pressed={metric === m}
            className={`px-3 py-1 text-xs rounded-full border transition-colors ${
              metric === m ? "bg-primary text-primary-foreground" : "bg-muted hover:bg-muted/80"
            }`}
          >
            {m.replace(/_/g, " ")}
          </button>
        ))}
      </div>

      {error && <ErrorBanner message={error} />}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">{metric.replace(/_/g, " ")} over time</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex justify-center py-8"><Loader2 className="animate-spin h-6 w-6" /></div>
          ) : (
            <TrendChart points={trends} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ─── Compare Tab ─────────────────────────────────────────────────────────────

function CompareTab({ results }: { results: UnifiedResult[] }) {
  const w9Results = results.filter((r): r is Extract<UnifiedResult, { _type: "w9" }> => r._type === "w9");
  const [runA, setRunA] = useState<string>("");
  const [runB, setRunB] = useState<string>("");
  const { comparison, loading, error, compare } = useBenchmarkCompare(runA, runB);

  if (w9Results.length < 2) {
    return <p className="text-sm text-muted-foreground py-8 text-center">Need at least 2 W9 runs to compare.</p>;
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-4 items-end flex-wrap">
        <div>
          <label className="text-xs text-muted-foreground block mb-1">Run A (baseline)</label>
          <select
            value={runA}
            onChange={(e) => setRunA(e.target.value)}
            className="border rounded px-3 py-1.5 text-sm bg-background"
          >
            <option value="">Select run...</option>
            {w9Results.map((r) => (
              <option key={r.run_id} value={r.run_id}>
                {r.dataset_id} — {fmtDate(r.timestamp)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs text-muted-foreground block mb-1">Run B (new)</label>
          <select
            value={runB}
            onChange={(e) => setRunB(e.target.value)}
            className="border rounded px-3 py-1.5 text-sm bg-background"
          >
            <option value="">Select run...</option>
            {w9Results.map((r) => (
              <option key={r.run_id} value={r.run_id}>
                {r.dataset_id} — {fmtDate(r.timestamp)}
              </option>
            ))}
          </select>
        </div>
        <button
          onClick={compare}
          disabled={!runA || !runB || loading}
          className="px-4 py-1.5 text-sm bg-primary text-primary-foreground rounded disabled:opacity-50"
        >
          {loading ? "Comparing..." : "Compare"}
        </button>
      </div>

      {error && <ErrorBanner message={error} />}

      {comparison && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm">Metric Deltas</CardTitle>
              {comparison.regression_detected ? (
                <Badge variant="destructive">Regression Detected</Badge>
              ) : (
                <Badge className="bg-green-600 text-white">No Regression</Badge>
              )}
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {Object.entries(comparison.metric_deltas)
                .sort(([, a], [, b]) => b - a)
                .map(([metric, delta]) => {
                  const isRegression = comparison.regression_metrics.includes(metric);
                  const isImprovement = comparison.improvement_metrics.includes(metric);
                  return (
                    <div key={metric} className="flex items-center justify-between text-sm">
                      <span className="font-mono text-xs">{metric}</span>
                      <span className={`font-mono text-sm ${
                        isRegression ? "text-destructive" : isImprovement ? "text-green-600" : "text-muted-foreground"
                      }`}>
                        {delta > 0 ? (
                          <><TrendingUp className="inline h-3 w-3 mr-1" />+{delta.toFixed(4)}</>
                        ) : delta < 0 ? (
                          <><TrendingDown className="inline h-3 w-3 mr-1" />{delta.toFixed(4)}</>
                        ) : (
                          `${delta.toFixed(4)}`
                        )}
                      </span>
                    </div>
                  );
                })}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ─── Config Card ────────────────────────────────────────────────────────────

function ConfigCard() {
  const [config, setConfig] = useState<BenchmarkConfig | null>(null);
  useEffect(() => {
    api
      .get<BenchmarkConfig>("/api/v1/benchmarks/config")
      .then(setConfig)
      .catch(() => {
        // Config is optional — don't block the page
      });
  }, []);

  if (!config) return null;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <Settings2 className="h-4 w-4" /> Benchmark Configuration
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
          <div>
            <p className="font-medium mb-1">W8 Peer Review</p>
            <div className="space-y-0.5 text-muted-foreground">
              <p>Corpus: <span className="font-mono text-foreground">{config.w8.corpus_version}</span></p>
              <p>Match mode: <span className="font-mono text-foreground">{config.w8.match_mode}</span></p>
              <p>Threshold: <span className="font-mono text-foreground">{config.w8.token_cosine_threshold}</span></p>
            </div>
          </div>
          <div>
            <p className="font-medium mb-1">W9 BioAgent Weights</p>
            <div className="space-y-0.5 text-muted-foreground">
              {Object.entries(config.w9.bioagent_weights).map(([k, v]) => (
                <p key={k}>{k.replace(/_/g, " ")}: <span className="font-mono text-foreground">{v}</span></p>
              ))}
              <p className="mt-1">Regression threshold: <span className="font-mono text-foreground">{config.w9.regression_threshold}</span></p>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export default function BenchmarksPage() {
  const [activeTab, setActiveTab] = useState<TabId>("results");
  const [visitedTabs, setVisitedTabs] = useState<Set<TabId>>(new Set(["results"]));
  const [resultsFilter, setResultsFilter] = useState<"all" | "w9" | "w8">("all");
  const { results, loading, error } = useBenchmarkResults();
  const { status: activeRun } = useBenchmarkActive();

  const handleTabChange = (tab: TabId) => {
    setActiveTab(tab);
    setVisitedTabs((prev) => new Set(prev).add(tab));
  };

  // Derive summary stats
  const w9Results = results.filter((r) => r._type === "w9");
  const w8Results = results.filter((r) => r._type === "w8");
  const latestW9Score = w9Results.length > 0 && w9Results[0]._type === "w9"
    ? w9Results[0].bioagent_score : null;
  const latestW8Recall = w8Results.length > 0 && w8Results[0]._type === "w8"
    ? w8Results[0].aggregate.overall_concern_recall_avg : null;

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Benchmarks</h1>
          <p className="text-sm text-muted-foreground">W9 bioinformatics & W8 peer review benchmark results</p>
        </div>
        {activeRun && activeRun.status !== "idle" && (
          <Badge className="bg-blue-600 text-white animate-pulse">
            <Activity className="h-3 w-3 mr-1" />
            Running: {activeRun.dataset_id || activeRun.suite_id}
          </Badge>
        )}
      </div>

      {error && <ErrorBanner message={error} />}

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <SummaryCard title="Total Runs" value={String(results.length)} sub={`${w9Results.length} W9 + ${w8Results.length} W8`} icon={Target} />
        <SummaryCard
          title="Latest BioAgent Score"
          value={latestW9Score != null ? fmtNum(latestW9Score) : "—"}
          sub="W9 composite"
          icon={Dna}
        />
        <SummaryCard
          title="Latest Concern Recall"
          value={latestW8Recall != null ? fmtNum(latestW8Recall) : "—"}
          sub="W8 peer review"
          icon={FileSearch}
        />
        <SummaryCard
          title="Active Run"
          value={activeRun?.status === "idle" ? "Idle" : activeRun?.status ?? "—"}
          icon={Activity}
        />
      </div>

      {/* Config */}
      <ConfigCard />

      {/* Tab Navigation */}
      <div className="flex border-b" role="tablist" aria-label="Benchmark views">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            onClick={() => handleTabChange(tab.id)}
            className={`flex items-center gap-1.5 px-4 py-2 text-sm border-b-2 transition-colors ${
              activeTab === tab.id
                ? "border-primary text-primary font-medium"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <tab.icon className="h-4 w-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content — lazy-mount on first visit, then display:none to preserve state */}
      <div role="tabpanel" style={{ display: activeTab === "results" ? undefined : "none" }}>
        <ResultsTab results={results} loading={loading} filter={resultsFilter} setFilter={setResultsFilter} />
      </div>
      {visitedTabs.has("datasets") && (
        <div role="tabpanel" style={{ display: activeTab === "datasets" ? undefined : "none" }}>
          <DatasetsTab />
        </div>
      )}
      {visitedTabs.has("trends") && (
        <div role="tabpanel" style={{ display: activeTab === "trends" ? undefined : "none" }}>
          <TrendsTab />
        </div>
      )}
      {visitedTabs.has("compare") && (
        <div role="tabpanel" style={{ display: activeTab === "compare" ? undefined : "none" }}>
          <CompareTab results={results} />
        </div>
      )}
    </div>
  );
}
