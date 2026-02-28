"use client";

import React, { useState, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api-client";

// ── Types ─────────────────────────────────────────────────────────────────────

interface AxisScore {
  axis: string;
  score: number;
  reasoning: string;
  key_evidence: string[];
}

interface ScoreResult {
  claim: string;
  mode: string;
  score: {
    R: number;
    C: number;
    M: number;
    X: number | null;
    T: number;
    composite: number | null;
  };
  composite: number | null;
  explanation: {
    axes: AxisScore[];
    x_applicable: boolean;
    overall_assessment: string;
    confidence_in_scoring: number;
  } | null;
}

interface CorpusEntry {
  claim_id: string;
  domain: string;
  claim_text: string;
  context: string;
  r_score: number | null;
  c_score: number | null;
  m_score: number | null;
  x_score: number | null;
  t_score: number | null;
  composite: number | null;
  uncertain: string;
  notes: string;
}

interface CorpusStats {
  total_claims: number;
  domains: Record<string, number>;
  mean_scores: Record<string, number | null>;
  entries: CorpusEntry[];
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const DOMAIN_COLORS: Record<string, string> = {
  spaceflight_biology: "#3b82f6",
  cancer_genomics: "#ef4444",
  neuroscience: "#a855f7",
};

const AXIS_COLORS: Record<string, string> = {
  R: "#14b8a6",
  C: "#f59e0b",
  M: "#3b82f6",
  X: "#8b5cf6",
  T: "#22c55e",
};

const AXIS_LABELS: Record<string, string> = {
  R: "Reproducibility",
  C: "Condition Specificity",
  M: "Methodology",
  X: "Cross-Omics",
  T: "Temporal Stability",
};

function scoreColor(val: number): string {
  if (val >= 0.75) return "#22c55e";
  if (val >= 0.5) return "#f59e0b";
  if (val >= 0.25) return "#ef4444";
  return "#6b7280";
}

function ScoreBar({ axis, value }: { axis: string; value: number | null }) {
  if (value === null) {
    return (
      <div className="flex items-center gap-2">
        <span className="w-4 text-xs font-mono text-muted-foreground">{axis}</span>
        <span className="text-xs text-muted-foreground">—</span>
      </div>
    );
  }
  const pct = Math.round(value * 100);
  return (
    <div className="flex items-center gap-2">
      <span className="w-4 text-xs font-mono text-muted-foreground">{axis}</span>
      <div className="flex-1 bg-muted rounded-full h-1.5 overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: AXIS_COLORS[axis] }}
        />
      </div>
      <span className="w-8 text-right text-xs font-mono" style={{ color: scoreColor(value) }}>
        {value.toFixed(2)}
      </span>
    </div>
  );
}

function DomainBadge({ domain }: { domain: string }) {
  const color = DOMAIN_COLORS[domain] ?? "#6b7280";
  const label = domain.replace(/_/g, " ");
  return (
    <span
      className="inline-block px-2 py-0.5 rounded text-[10px] font-medium"
      style={{ background: `${color}22`, color }}
    >
      {label}
    </span>
  );
}

function UncertainBadges({ uncertain }: { uncertain: string }) {
  if (!uncertain) return null;
  const axes = uncertain.split(",").map((a) => a.trim()).filter(Boolean);
  return (
    <div className="flex gap-1 flex-wrap">
      {axes.map((ax) => (
        <span
          key={ax}
          className="text-[9px] px-1 py-0 rounded border border-amber-500/40 text-amber-400"
        >
          {ax}?
        </span>
      ))}
    </div>
  );
}

// ── Claim Scorer Tab ──────────────────────────────────────────────────────────

function ClaimScorerTab() {
  const [claim, setClaim] = useState("");
  const [context, setContext] = useState("");
  const [mode, setMode] = useState<"llm" | "heuristic">("llm");
  const [result, setResult] = useState<ScoreResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const score = useCallback(async () => {
    if (!claim.trim() || claim.length < 10) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await api.post<ScoreResult>("/api/v1/rcmxt/score", { claim, context, mode });
      setResult(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Scoring failed");
    } finally {
      setLoading(false);
    }
  }, [claim, context, mode]);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Score a Biological Claim</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground font-medium">Claim Text</label>
            <Textarea
              value={claim}
              onChange={(e) => setClaim(e.target.value)}
              placeholder="Enter a specific, testable biological claim (min 10 chars)…"
              className="text-sm min-h-[80px] resize-none"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground font-medium">Domain Context (optional)</label>
            <Input
              value={context}
              onChange={(e) => setContext(e.target.value)}
              placeholder="e.g. 'TCGA pan-cancer, 2013. N=10,000+ tumors.'"
              className="text-sm"
            />
          </div>
          <div className="flex items-center gap-3">
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground font-medium">Mode</label>
              <Select value={mode} onValueChange={(v) => setMode(v as "llm" | "heuristic")}>
                <SelectTrigger className="w-36 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="llm">LLM (Sonnet)</SelectItem>
                  <SelectItem value="heuristic">Heuristic (fast)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button
              size="sm"
              onClick={score}
              disabled={loading || claim.length < 10}
              className="mt-5"
            >
              {loading ? "Scoring…" : "Score Claim"}
            </Button>
          </div>

          {error && (
            <p className="text-xs text-destructive">{error}</p>
          )}
        </CardContent>
      </Card>

      {result && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm">RCMXT Scores</CardTitle>
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="text-[10px]">
                  {result.mode}
                </Badge>
                {result.composite !== null && (
                  <span
                    className="text-sm font-mono font-semibold"
                    style={{ color: scoreColor(result.composite) }}
                  >
                    {result.composite.toFixed(3)}
                  </span>
                )}
              </div>
            </div>
            <p className="text-xs text-muted-foreground truncate" title={result.claim}>
              {result.claim.length > 100 ? result.claim.slice(0, 97) + "…" : result.claim}
            </p>
          </CardHeader>
          <CardContent className="space-y-2">
            {/* Axis bars */}
            <div className="space-y-1.5">
              {(["R", "C", "M", "X", "T"] as const).map((ax) => (
                <ScoreBar key={ax} axis={ax} value={result.score[ax]} />
              ))}
            </div>

            {/* LLM explanation */}
            {result.explanation && (
              <div className="mt-4 space-y-3">
                <div className="rounded bg-accent/40 p-3">
                  <p className="text-xs font-medium text-muted-foreground mb-1">Overall Assessment</p>
                  <p className="text-xs text-foreground">{result.explanation.overall_assessment}</p>
                  <p className="text-[10px] text-muted-foreground mt-1">
                    Scorer confidence: {Math.round(result.explanation.confidence_in_scoring * 100)}%
                  </p>
                </div>

                <div className="space-y-2">
                  {result.explanation.axes.map((ae) => (
                    <div key={ae.axis} className="rounded border border-border p-2">
                      <div className="flex items-center gap-2 mb-1">
                        <span
                          className="text-xs font-mono font-semibold px-1.5 py-0.5 rounded"
                          style={{
                            background: `${AXIS_COLORS[ae.axis]}22`,
                            color: AXIS_COLORS[ae.axis],
                          }}
                        >
                          {ae.axis}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {AXIS_LABELS[ae.axis]}
                        </span>
                        <span className="ml-auto text-xs font-mono" style={{ color: scoreColor(ae.score) }}>
                          {ae.score.toFixed(2)}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground leading-relaxed">{ae.reasoning}</p>
                      {ae.key_evidence.length > 0 && (
                        <p className="text-[10px] text-muted-foreground mt-1">
                          PMIDs/DOIs: {ae.key_evidence.join(", ")}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ── Corpus Tab ────────────────────────────────────────────────────────────────

function CorpusTab() {
  const [stats, setStats] = useState<CorpusStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [domain, setDomain] = useState("all");
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const q = domain !== "all" ? `?domain=${domain}` : "";
      const data = await api.get<CorpusStats>(`/api/v1/rcmxt/corpus-stats${q}`);
      setStats(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [domain]);

  // Load on mount and domain change
  React.useEffect(() => {
    load();
  }, [load]);

  const entries = stats?.entries ?? [];
  const filtered = search
    ? entries.filter(
        (e) =>
          e.claim_text.toLowerCase().includes(search.toLowerCase()) ||
          e.claim_id.toLowerCase().includes(search.toLowerCase()),
      )
    : entries;

  return (
    <div className="space-y-4">
      {/* Header stats */}
      {stats && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Card>
            <CardContent className="p-3">
              <p className="text-xs text-muted-foreground">Total Claims</p>
              <p className="text-2xl font-bold">{stats.total_claims}</p>
            </CardContent>
          </Card>
          {Object.entries(stats.domains).map(([d, n]) => (
            <Card key={d}>
              <CardContent className="p-3">
                <p className="text-xs text-muted-foreground truncate">{d.replace(/_/g, " ")}</p>
                <p className="text-2xl font-bold">{n}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Mean scores */}
      {stats?.mean_scores && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs text-muted-foreground uppercase tracking-wider">
              Corpus Mean Scores
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5">
            {Object.entries(stats.mean_scores)
              .filter(([, v]) => v !== null)
              .map(([ax, val]) => (
                <ScoreBar key={ax} axis={ax} value={val} />
              ))}
          </CardContent>
        </Card>
      )}

      {/* Filters */}
      <div className="flex gap-2">
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search claims…"
          className="text-sm max-w-xs"
        />
        <Select value={domain} onValueChange={setDomain}>
          <SelectTrigger className="w-44 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Domains</SelectItem>
            <SelectItem value="spaceflight_biology">Spaceflight Biology</SelectItem>
            <SelectItem value="cancer_genomics">Cancer Genomics</SelectItem>
            <SelectItem value="neuroscience">Neuroscience</SelectItem>
          </SelectContent>
        </Select>
        {loading && <span className="text-xs text-muted-foreground self-center">Loading…</span>}
      </div>

      {/* Table */}
      <div className="rounded border border-border overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="text-xs w-20">ID</TableHead>
              <TableHead className="text-xs">Claim</TableHead>
              <TableHead className="text-xs w-24">Domain</TableHead>
              <TableHead className="text-xs w-8 text-center">R</TableHead>
              <TableHead className="text-xs w-8 text-center">C</TableHead>
              <TableHead className="text-xs w-8 text-center">M</TableHead>
              <TableHead className="text-xs w-8 text-center">X</TableHead>
              <TableHead className="text-xs w-8 text-center">T</TableHead>
              <TableHead className="text-xs w-14 text-center">Score</TableHead>
              <TableHead className="text-xs w-16">Flags</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((entry) => (
              <React.Fragment key={entry.claim_id}>
                <TableRow
                  className="cursor-pointer hover:bg-accent/30"
                  onClick={() =>
                    setExpanded(expanded === entry.claim_id ? null : entry.claim_id)
                  }
                >
                  <TableCell className="text-xs font-mono py-2">{entry.claim_id}</TableCell>
                  <TableCell className="text-xs py-2 max-w-[280px]">
                    <span className="line-clamp-2" title={entry.claim_text}>
                      {entry.claim_text}
                    </span>
                  </TableCell>
                  <TableCell className="py-2">
                    <DomainBadge domain={entry.domain} />
                  </TableCell>
                  {(["r_score", "c_score", "m_score", "x_score", "t_score"] as const).map(
                    (k) => (
                      <TableCell key={k} className="text-center text-xs font-mono py-2">
                        {entry[k] !== null ? (
                          <span style={{ color: scoreColor(entry[k]!) }}>
                            {entry[k]!.toFixed(2)}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                    ),
                  )}
                  <TableCell className="text-center text-xs font-mono font-semibold py-2">
                    {entry.composite !== null ? (
                      <span style={{ color: scoreColor(entry.composite) }}>
                        {entry.composite.toFixed(2)}
                      </span>
                    ) : (
                      "—"
                    )}
                  </TableCell>
                  <TableCell className="py-2">
                    <UncertainBadges uncertain={entry.uncertain} />
                  </TableCell>
                </TableRow>

                {expanded === entry.claim_id && (
                  <TableRow className="bg-accent/20">
                    <TableCell colSpan={10} className="py-3 px-4">
                      <div className="space-y-2 text-xs">
                        <p className="text-foreground">{entry.claim_text}</p>
                        <p className="text-muted-foreground italic">{entry.context}</p>
                        {entry.notes && (
                          <p className="text-amber-400/80 text-[10px]">Note: {entry.notes}</p>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                )}
              </React.Fragment>
            ))}
            {filtered.length === 0 && (
              <TableRow>
                <TableCell colSpan={10} className="text-center text-xs text-muted-foreground py-8">
                  No claims found.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

// ── Batch Scorer Tab ──────────────────────────────────────────────────────────

interface BatchResult {
  total_claims: number;
  mode: string;
  results: Array<{
    claim_id: string;
    claim_text: string;
    scores: { R: number; C: number; M: number; X: number | null; T: number };
    composite: number | null;
    ground_truth_diff: Record<string, number> | null;
    explanation?: {
      overall_assessment: string;
      confidence_in_scoring: number;
    };
  }>;
  axis_summary: Record<
    string,
    { axis: string; scores: number[]; mean: number; std: number; mae_vs_ground_truth: number | null }
  >;
}

function BatchScorerTab() {
  const [csv, setCsv] = useState(
    `claim_id,claim_text,context\nSB-001,"Long-duration spaceflight causes ~54% increase in red blood cell hemolysis.","Trudel et al. 2022"\nCG-001,"KRAS G12C mutation predicts sensitivity to sotorasib in NSCLC.","CodeBreaK200 Phase III RCT"`,
  );
  const [mode, setMode] = useState<"llm" | "heuristic">("llm");
  const [runs, setRuns] = useState(1);
  const [result, setResult] = useState<BatchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const parseCsv = (text: string) => {
    const lines = text.trim().split("\n");
    if (lines.length < 2) return [];
    const headers = lines[0].split(",").map((h) => h.trim().replace(/^"|"$/g, ""));
    return lines.slice(1).map((line) => {
      const vals = line.split(/,(?=(?:[^"]*"[^"]*")*[^"]*$)/).map((v) =>
        v.trim().replace(/^"|"$/g, ""),
      );
      const obj: Record<string, string> = {};
      headers.forEach((h, i) => {
        obj[h] = vals[i] ?? "";
      });
      return obj;
    });
  };

  const runBatch = useCallback(async () => {
    const rows = parseCsv(csv);
    if (rows.length === 0) return;
    const claims = rows.map((r) => ({
      claim_id: r.claim_id || `C${rows.indexOf(r) + 1}`,
      claim_text: r.claim_text || r.claim || "",
      context: r.context || "",
    }));
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await api.post<BatchResult>("/api/v1/rcmxt/batch", {
        claims,
        mode,
        runs_per_claim: runs,
      });
      setResult(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Batch scoring failed");
    } finally {
      setLoading(false);
    }
  }, [csv, mode, runs]);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Batch RCMXT Scorer</CardTitle>
          <p className="text-xs text-muted-foreground">
            Paste CSV with columns: <code className="text-xs bg-accent px-1 rounded">claim_id, claim_text, context</code>
          </p>
        </CardHeader>
        <CardContent className="space-y-3">
          <Textarea
            value={csv}
            onChange={(e) => setCsv(e.target.value)}
            className="text-xs font-mono min-h-[120px] resize-y"
          />
          <div className="flex items-center gap-3 flex-wrap">
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground font-medium">Mode</label>
              <Select value={mode} onValueChange={(v) => setMode(v as "llm" | "heuristic")}>
                <SelectTrigger className="w-36 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="llm">LLM (Sonnet)</SelectItem>
                  <SelectItem value="heuristic">Heuristic</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground font-medium">Runs/Claim</label>
              <Input
                type="number"
                min={1}
                max={5}
                value={runs}
                onChange={(e) => setRuns(Math.max(1, Math.min(5, parseInt(e.target.value) || 1)))}
                className="w-20 text-xs"
              />
            </div>
            <Button size="sm" onClick={runBatch} disabled={loading} className="mt-5">
              {loading ? "Scoring…" : "Run Batch"}
            </Button>
          </div>
          {error && <p className="text-xs text-destructive">{error}</p>}
        </CardContent>
      </Card>

      {result && (
        <>
          {/* Axis summary */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">
                Axis Summary — {result.total_claims} claims · {result.mode}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
                {Object.values(result.axis_summary).map((ax) => (
                  <div key={ax.axis} className="space-y-1">
                    <p
                      className="text-xs font-mono font-semibold"
                      style={{ color: AXIS_COLORS[ax.axis] }}
                    >
                      {ax.axis} — {AXIS_LABELS[ax.axis]}
                    </p>
                    <p className="text-lg font-bold" style={{ color: scoreColor(ax.mean) }}>
                      {ax.mean.toFixed(3)}
                    </p>
                    <p className="text-[10px] text-muted-foreground">
                      σ={ax.std.toFixed(3)}
                      {ax.mae_vs_ground_truth !== null && (
                        <span className="ml-1">MAE={ax.mae_vs_ground_truth.toFixed(3)}</span>
                      )}
                    </p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Per-claim results */}
          <div className="rounded border border-border overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs w-20">ID</TableHead>
                  <TableHead className="text-xs">Claim</TableHead>
                  <TableHead className="text-xs w-8 text-center">R</TableHead>
                  <TableHead className="text-xs w-8 text-center">C</TableHead>
                  <TableHead className="text-xs w-8 text-center">M</TableHead>
                  <TableHead className="text-xs w-8 text-center">X</TableHead>
                  <TableHead className="text-xs w-8 text-center">T</TableHead>
                  <TableHead className="text-xs w-14 text-center">Score</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {result.results.map((r) => (
                  <TableRow key={r.claim_id}>
                    <TableCell className="text-xs font-mono py-2">{r.claim_id}</TableCell>
                    <TableCell className="text-xs py-2 max-w-[280px] truncate" title={r.claim_text}>
                      {r.claim_text}
                    </TableCell>
                    {(["R", "C", "M", "X", "T"] as const).map((ax) => (
                      <TableCell key={ax} className="text-center text-xs font-mono py-2">
                        {r.scores[ax] !== null ? (
                          <span style={{ color: scoreColor(r.scores[ax] as number) }}>
                            {(r.scores[ax] as number).toFixed(2)}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                    ))}
                    <TableCell className="text-center text-xs font-mono font-semibold py-2">
                      {r.composite !== null ? (
                        <span style={{ color: scoreColor(r.composite) }}>
                          {r.composite.toFixed(3)}
                        </span>
                      ) : (
                        "—"
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function RcmxtPage() {
  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold">RCMXT Calibration</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Evidence confidence scoring — Reproducibility · Condition · Methodology · Cross-Omics ·
          Temporal
        </p>
      </div>

      {/* Framework reference */}
      <div className="grid grid-cols-5 gap-2">
        {Object.entries(AXIS_LABELS).map(([ax, label]) => (
          <div
            key={ax}
            className="rounded border border-border p-2 text-center"
            style={{ borderColor: `${AXIS_COLORS[ax]}44` }}
          >
            <p className="text-lg font-bold" style={{ color: AXIS_COLORS[ax] }}>
              {ax}
            </p>
            <p className="text-[10px] text-muted-foreground leading-tight">{label}</p>
          </div>
        ))}
      </div>

      <Tabs defaultValue="scorer">
        <TabsList>
          <TabsTrigger value="scorer">Claim Scorer</TabsTrigger>
          <TabsTrigger value="corpus">Corpus ({15})</TabsTrigger>
          <TabsTrigger value="batch">Batch Score</TabsTrigger>
        </TabsList>

        <TabsContent value="scorer" className="mt-4">
          <ClaimScorerTab />
        </TabsContent>

        <TabsContent value="corpus" className="mt-4">
          <CorpusTab />
        </TabsContent>

        <TabsContent value="batch" className="mt-4">
          <BatchScorerTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
