"use client";

import React, { useState, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  FlaskConical,
  Play,
  CheckCircle2,
  XCircle,
  Loader2,
  Copy,
  Download,
  AlertCircle,
  Pause,
} from "lucide-react";
import { api } from "@/lib/api-client";
import type { CreateWorkflowResponse } from "@/types/api";

// ─── W10 Pipeline Step Definitions ───────────────────────────────────────────

const W10_STEPS = [
  { id: "SCOPE", label: "Define Research Scope", type: "hc" as const },
  { id: "COMPOUND_SEARCH", label: "Compound Search (ChEMBL)", type: "mcp" as const },
  { id: "BIOACTIVITY_PROFILE", label: "Bioactivity Profile (ChEMBL)", type: "mcp" as const },
  { id: "TARGET_IDENTIFICATION", label: "Target Identification", type: "llm" as const },
  { id: "CLINICAL_TRIALS_SEARCH", label: "Clinical Trials Search (CT.gov)", type: "mcp" as const },
  { id: "EFFICACY_ANALYSIS", label: "Efficacy Analysis", type: "llm" as const },
  { id: "SAFETY_PROFILE", label: "Safety & ADMET Profile (ChEMBL)", type: "mcp" as const },
  { id: "DC_PRELIMINARY", label: "Preliminary Direction Check", type: "dc" as const },
  { id: "MECHANISM_REVIEW", label: "Mechanism of Action Review", type: "llm" as const },
  { id: "LITERATURE_COMPARISON", label: "Literature & Novelty Comparison", type: "llm" as const },
  { id: "GRANT_RELEVANCE", label: "Grant Funding Assessment", type: "llm" as const },
  { id: "REPORT", label: "Build Final Report", type: "report" as const },
];

type StepType = "hc" | "dc" | "mcp" | "llm" | "report";
type StepState = "pending" | "running" | "completed" | "skipped" | "failed";

interface StepStatus {
  state: StepState;
  summary?: string;
  duration_ms?: number;
}

const STEP_TYPE_COLORS: Record<StepType, string> = {
  hc: "text-amber-500",
  dc: "text-purple-500",
  mcp: "text-blue-500",
  llm: "text-emerald-500",
  report: "text-green-600",
};

const STEP_TYPE_BADGE: Record<StepType, string> = {
  hc: "HC",
  dc: "DC",
  mcp: "MCP",
  llm: "LLM",
  report: "RPT",
};

// ─── Lightweight Markdown Renderer ────────────────────────────────────────────

function MarkdownSection({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <div className="space-y-1 text-sm leading-relaxed">
      {lines.map((line, i) => {
        if (line.startsWith("# "))
          return <h1 key={i} className="text-xl font-bold mt-4 mb-2">{line.slice(2)}</h1>;
        if (line.startsWith("## "))
          return <h2 key={i} className="text-base font-semibold mt-3 mb-1 text-primary">{line.slice(3)}</h2>;
        if (line.startsWith("### "))
          return <h3 key={i} className="text-sm font-medium mt-2 mb-1">{line.slice(4)}</h3>;
        if (line.startsWith("- "))
          return <li key={i} className="ml-4 list-disc">{line.slice(2)}</li>;
        if (line === "---")
          return <hr key={i} className="border-border my-3" />;
        if (line === "")
          return <div key={i} className="h-1.5" />;
        // Bold inline **text**
        const boldParts = line.split(/\*\*(.*?)\*\*/g);
        if (boldParts.length > 1) {
          return (
            <p key={i}>
              {boldParts.map((part, j) =>
                j % 2 === 1 ? <strong key={j}>{part}</strong> : part,
              )}
            </p>
          );
        }
        if (line.startsWith("*") && line.endsWith("*") && line.length > 2)
          return <p key={i} className="italic text-muted-foreground text-xs">{line.slice(1, -1)}</p>;
        return <p key={i}>{line}</p>;
      })}
    </div>
  );
}

// ─── Step Progress Item ───────────────────────────────────────────────────────

function StepItem({
  step,
  status,
  index,
}: {
  step: (typeof W10_STEPS)[0];
  status: StepStatus;
  index: number;
}) {
  const icon =
    status.state === "completed" ? (
      <CheckCircle2 className="h-4 w-4 text-green-500" />
    ) : status.state === "running" ? (
      <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
    ) : status.state === "failed" ? (
      <XCircle className="h-4 w-4 text-red-500" />
    ) : status.state === "skipped" ? (
      <CheckCircle2 className="h-4 w-4 text-muted-foreground" />
    ) : (
      <div className="h-4 w-4 rounded-full border-2 border-muted-foreground/30" />
    );

  const typeColor = STEP_TYPE_COLORS[step.type];

  return (
    <div className="flex items-start gap-3 py-1.5">
      <div className="mt-0.5 shrink-0">{icon}</div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span
            className={
              status.state === "running"
                ? "text-sm font-medium text-blue-600"
                : status.state === "completed"
                  ? "text-sm font-medium"
                  : "text-sm text-muted-foreground"
            }
          >
            {index + 1}. {step.label}
          </span>
          <Badge
            variant="outline"
            className={`text-[9px] px-1 py-0 h-4 shrink-0 ${typeColor}`}
          >
            {STEP_TYPE_BADGE[step.type]}
          </Badge>
          {status.duration_ms != null && (
            <span className="text-xs text-muted-foreground">
              {status.duration_ms > 1000
                ? `${(status.duration_ms / 1000).toFixed(1)}s`
                : `${status.duration_ms}ms`}
            </span>
          )}
        </div>
        {status.summary && status.state !== "pending" && (
          <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{status.summary}</p>
        )}
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function DrugDiscoveryPage() {
  const [query, setQuery] = useState("");
  const [budget, setBudget] = useState("15.0");
  const [running, setRunning] = useState(false);
  const [workflowId, setWorkflowId] = useState<string | null>(null);
  const [stepStatuses, setStepStatuses] = useState<Record<string, StepStatus>>({});
  const [markdownReport, setMarkdownReport] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [reportCopied, setReportCopied] = useState(false);
  const [waitingHuman, setWaitingHuman] = useState(false);
  const [resuming, setResuming] = useState(false);
  const sseRef = useRef<EventSource | null>(null);

  const completedCount = Object.values(stepStatuses).filter(
    (s) => s.state === "completed" || s.state === "skipped",
  ).length;
  const progress = Math.round((completedCount / W10_STEPS.length) * 100);

  function stopSSE() {
    if (sseRef.current) {
      sseRef.current.close();
      sseRef.current = null;
    }
  }

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!query.trim()) return;

    setRunning(true);
    setWaitingHuman(false);
    setError("");
    setMarkdownReport("");
    setStepStatuses({});
    setWorkflowId(null);
    stopSSE();

    try {
      const res = await api.post<CreateWorkflowResponse>("/api/v1/workflows", {
        template: "W10",
        query: query.trim(),
        budget: parseFloat(budget) || 15.0,
      });

      const wid = res.workflow_id;
      setWorkflowId(wid);

      const token = typeof window !== "undefined" ? localStorage.getItem("bioteam_api_key") : null;
      const sseUrl = `/api/v1/sse/workflow/${wid}${token ? `?token=${token}` : ""}`;
      const es = new EventSource(
        `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}${sseUrl}`,
      );
      sseRef.current = es;

      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          const etype = data.event_type as string;

          if (etype === "workflow.step_started" || etype === "workflow.step_start") {
            const sid = data.step_id as string;
            setStepStatuses((prev) => ({
              ...prev,
              [sid]: { state: "running" },
            }));
          } else if (etype === "workflow.step_completed" || etype === "workflow.step_complete") {
            const sid = data.step_id as string;
            const payload = data.payload ?? {};
            setStepStatuses((prev) => ({
              ...prev,
              [sid]: {
                state: "completed",
                summary: payload.summary as string | undefined,
                duration_ms: payload.duration_ms as number | undefined,
              },
            }));
          } else if (etype === "workflow.step_failed" || etype === "workflow.step_error") {
            const sid = data.step_id as string;
            setStepStatuses((prev) => ({
              ...prev,
              [sid]: { state: "failed", summary: data.payload?.error as string | undefined },
            }));
          } else if (etype === "workflow.waiting_human" || etype === "workflow.human_checkpoint") {
            setWaitingHuman(true);
          } else if (etype === "workflow.direction_check") {
            // DC step — auto-continues
            const sid = data.step_id as string;
            setStepStatuses((prev) => ({
              ...prev,
              [sid]: { state: "completed", summary: "Direction check — auto-continuing" },
            }));
          } else if (etype === "workflow.completed") {
            stopSSE();
            fetchReport(wid);
          } else if (etype === "workflow.failed") {
            stopSSE();
            setError(data.payload?.error ?? "Workflow failed");
            setRunning(false);
          }
        } catch {
          // non-JSON SSE message, ignore
        }
      };

      es.onerror = () => {
        stopSSE();
        fetchReport(wid);
      };
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setRunning(false);
    }
  }

  async function fetchReport(wid: string) {
    try {
      const result = await api.get<{
        step_results?: Record<string, { output?: Record<string, unknown> }>;
        state?: string;
        session_manifest?: Record<string, unknown>;
      }>(`/api/v1/workflows/${wid}`);

      // W10 stores report in session_manifest["w10_report"]
      const reportFromManifest = result.session_manifest?.["w10_report"] as string | undefined;
      const reportStep = result.step_results?.["REPORT"];
      const output = reportStep?.output as Record<string, unknown> | undefined;
      const reportFromStep = output?.["report_markdown"] as string | undefined;

      const md = reportFromManifest || reportFromStep;
      if (md) setMarkdownReport(md);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch report");
    } finally {
      setRunning(false);
    }
  }

  function handleCopy() {
    if (!markdownReport) return;
    navigator.clipboard.writeText(markdownReport);
    setReportCopied(true);
    setTimeout(() => setReportCopied(false), 2000);
  }

  function handleDownload() {
    if (!markdownReport) return;
    const blob = new Blob([markdownReport], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `drug_discovery_${query.replace(/\s+/g, "_").toLowerCase()}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function handleResume() {
    if (!workflowId || resuming) return;
    setResuming(true);
    setError("");
    try {
      await api.post(`/api/v1/workflows/${workflowId}/intervene`, { action: "resume" });
      setWaitingHuman(false);
      setRunning(true);

      // Re-subscribe to SSE for the resumed pipeline
      stopSSE();
      const token = typeof window !== "undefined" ? localStorage.getItem("bioteam_api_key") : null;
      const sseUrl = `/api/v1/sse/workflow/${workflowId}${token ? `?token=${token}` : ""}`;
      const es = new EventSource(
        `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}${sseUrl}`,
      );
      sseRef.current = es;

      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          const etype = data.event_type as string;
          if (etype === "workflow.step_started" || etype === "workflow.step_start") {
            const sid = data.step_id as string;
            setStepStatuses((prev) => ({ ...prev, [sid]: { state: "running" } }));
          } else if (etype === "workflow.step_completed" || etype === "workflow.step_complete") {
            const sid = data.step_id as string;
            const payload = data.payload ?? {};
            setStepStatuses((prev) => ({
              ...prev,
              [sid]: {
                state: "completed",
                summary: payload.summary as string | undefined,
                duration_ms: payload.duration_ms as number | undefined,
              },
            }));
          } else if (etype === "workflow.step_failed" || etype === "workflow.step_error") {
            const sid = data.step_id as string;
            setStepStatuses((prev) => ({
              ...prev,
              [sid]: { state: "failed", summary: data.payload?.error as string | undefined },
            }));
          } else if (etype === "workflow.waiting_human" || etype === "workflow.human_checkpoint") {
            setWaitingHuman(true);
          } else if (etype === "workflow.direction_check") {
            const sid = data.step_id as string;
            setStepStatuses((prev) => ({
              ...prev,
              [sid]: { state: "completed", summary: "Direction check — auto-continuing" },
            }));
          } else if (etype === "workflow.completed") {
            stopSSE();
            fetchReport(workflowId);
          } else if (etype === "workflow.failed") {
            stopSSE();
            setError(data.payload?.error ?? "Workflow failed");
            setRunning(false);
          }
        } catch {
          // non-JSON SSE, ignore
        }
      };
      es.onerror = () => {
        stopSSE();
        fetchReport(workflowId);
      };
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to resume workflow");
    } finally {
      setResuming(false);
    }
  }

  const hasReport = markdownReport.length > 0;

  return (
    <div className="flex flex-col gap-6 p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3">
        <FlaskConical className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold">W10 Drug Discovery</h1>
          <p className="text-sm text-muted-foreground">
            12-step pipeline — ChEMBL compound screening, bioactivity, ADMET,
            ClinicalTrials.gov, mechanism review, grant assessment
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* ── Left column: Form + Pipeline Progress ── */}
        <div className="space-y-4">
          {/* Input form */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Query</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-3">
                <div className="space-y-1">
                  <label htmlFor="compound-query" className="text-sm font-medium">
                    Compound / Target
                  </label>
                  <Input
                    id="compound-query"
                    placeholder="e.g. imatinib, EGFR inhibitors, BCR-ABL"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    disabled={running}
                    className="text-sm"
                  />
                </div>
                <div className="space-y-1">
                  <label htmlFor="budget" className="text-sm font-medium">
                    Budget ($)
                  </label>
                  <Input
                    id="budget"
                    type="number"
                    min="1"
                    max="50"
                    step="0.5"
                    value={budget}
                    onChange={(e) => setBudget(e.target.value)}
                    disabled={running}
                    className="text-sm w-28"
                  />
                </div>
                <Button
                  type="submit"
                  disabled={running || !query.trim()}
                  className="w-full gap-2"
                >
                  {running ? (
                    <><Loader2 className="h-4 w-4 animate-spin" /> Running…</>
                  ) : (
                    <><Play className="h-4 w-4" /> Run Analysis</>
                  )}
                </Button>
              </form>
            </CardContent>
          </Card>

          {/* Human checkpoint notification */}
          {waitingHuman && (
            <Card className="border-amber-500/50 bg-amber-500/10">
              <CardContent className="pt-4">
                <div className="flex items-start gap-2">
                  <Pause className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-amber-700 dark:text-amber-400">
                      Human Checkpoint — SCOPE Review
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Review the research scope definition above, then approve
                      to continue the analysis pipeline.
                    </p>
                  </div>
                </div>
                <Button
                  size="sm"
                  className="mt-3 w-full gap-2 bg-amber-500 hover:bg-amber-600 text-white"
                  onClick={handleResume}
                  disabled={resuming}
                >
                  {resuming ? (
                    <><Loader2 className="h-3.5 w-3.5 animate-spin" /> Resuming…</>
                  ) : (
                    <><Play className="h-3.5 w-3.5" /> Approve &amp; Resume</>
                  )}
                </Button>
              </CardContent>
            </Card>
          )}

          {/* Error */}
          {error && (
            <Card className="border-destructive/50 bg-destructive/10">
              <CardContent className="pt-4 flex items-start gap-2">
                <AlertCircle className="h-4 w-4 text-destructive shrink-0 mt-0.5" />
                <p className="text-sm text-destructive">{error}</p>
              </CardContent>
            </Card>
          )}

          {/* Pipeline progress */}
          {workflowId && (
            <Card>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm">Pipeline</CardTitle>
                  <span className="text-xs text-muted-foreground">{progress}%</span>
                </div>
                <Progress value={progress} className="h-1.5" />
              </CardHeader>
              <CardContent className="pt-0">
                <div className="space-y-0.5">
                  {W10_STEPS.map((step, idx) => (
                    <StepItem
                      key={step.id}
                      step={step}
                      index={idx}
                      status={stepStatuses[step.id] ?? { state: "pending" }}
                    />
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Step type legend */}
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-muted-foreground px-1">
            <span className="text-amber-500 font-medium">HC</span> Human Checkpoint
            <span className="text-purple-500 font-medium ml-2">DC</span> Direction Check
            <span className="text-blue-500 font-medium ml-2">MCP</span> External DB
            <span className="text-emerald-500 font-medium ml-2">LLM</span> AI Analysis
          </div>
        </div>

        {/* ── Right column (2/3): Report ── */}
        <div className="lg:col-span-2">
          <Card className="h-full min-h-[400px]">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Analysis Report</CardTitle>
                {hasReport && (
                  <div className="flex gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 gap-1.5 text-xs"
                      onClick={handleCopy}
                    >
                      <Copy className="h-3.5 w-3.5" />
                      {reportCopied ? "Copied!" : "Copy"}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 gap-1.5 text-xs"
                      onClick={handleDownload}
                    >
                      <Download className="h-3.5 w-3.5" />
                      .md
                    </Button>
                  </div>
                )}
              </div>
            </CardHeader>
            <CardContent>
              {hasReport ? (
                <div className="prose prose-sm dark:prose-invert max-w-none">
                  <MarkdownSection text={markdownReport} />
                </div>
              ) : running ? (
                <div className="flex flex-col items-center justify-center py-16 gap-3 text-muted-foreground">
                  <Loader2 className="h-8 w-8 animate-spin" />
                  <p className="text-sm">Analysis in progress…</p>
                  {workflowId && (
                    <p className="text-xs font-mono opacity-60">
                      {workflowId.slice(0, 12)}…
                    </p>
                  )}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-16 gap-3 text-muted-foreground">
                  <FlaskConical className="h-10 w-10 opacity-20" />
                  <p className="text-sm">
                    Enter a compound or target to begin analysis.
                  </p>
                  <div className="text-xs text-center max-w-xs space-y-1 opacity-70">
                    <p>Examples: <em>imatinib</em>, <em>EGFR inhibitors</em>,</p>
                    <p><em>venetoclax BCL-2</em>, <em>PD-1 checkpoint</em></p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
