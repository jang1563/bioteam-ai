"use client";

import React, { useState, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Progress } from "@/components/ui/progress";
import {
  FileSearch,
  Play,
  CheckCircle2,
  XCircle,
  Loader2,
  Clock,
  ChevronDown,
  ChevronUp,
  Copy,
  Download,
} from "lucide-react";
import { api } from "@/lib/api-client";
import type { CreateWorkflowResponse } from "@/types/api";

// ─── W8 Pipeline Step Definitions ────────────────────────────────────────────

const W8_STEPS = [
  { id: "INGEST", label: "Ingest Paper" },
  { id: "PARSE_SECTIONS", label: "Parse Sections" },
  { id: "EXTRACT_CLAIMS", label: "Extract Claims" },
  { id: "CITE_VALIDATION", label: "Citation Validation" },
  { id: "BACKGROUND_LIT", label: "Background Literature" },
  { id: "NOVELTY_CHECK", label: "Novelty Assessment" },
  { id: "INTEGRITY_AUDIT", label: "Data Integrity Audit" },
  { id: "CONTRADICTION_CHECK", label: "Contradiction Detection" },
  { id: "METHODOLOGY_REVIEW", label: "Methodology Review" },
  { id: "EVIDENCE_GRADE", label: "Evidence Grading (RCMXT)" },
  { id: "HUMAN_CHECKPOINT", label: "Human Checkpoint" },
  { id: "SYNTHESIZE_REVIEW", label: "Synthesize Review" },
  { id: "REPORT", label: "Build Report" },
];

type StepState = "pending" | "running" | "completed" | "skipped" | "failed";

interface StepStatus {
  state: StepState;
  summary?: string;
  cost?: number;
  duration_ms?: number;
}

// ─── Markdown Renderer (lightweight) ─────────────────────────────────────────

function MarkdownSection({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <div className="space-y-1 font-mono text-sm leading-relaxed">
      {lines.map((line, i) => {
        if (line.startsWith("# "))
          return <h1 key={i} className="text-2xl font-bold mt-4 mb-2">{line.slice(2)}</h1>;
        if (line.startsWith("## "))
          return <h2 key={i} className="text-lg font-semibold mt-4 mb-1 text-primary">{line.slice(3)}</h2>;
        if (line.startsWith("### "))
          return <h3 key={i} className="text-base font-medium mt-3 mb-1">{line.slice(4)}</h3>;
        if (line.startsWith("- "))
          return <li key={i} className="ml-4 list-disc">{line.slice(2)}</li>;
        if (line.match(/^\d+\./))
          return <li key={i} className="ml-4 list-decimal">{line.slice(line.indexOf(".") + 2)}</li>;
        if (line.startsWith("*") && line.endsWith("*") && line.length > 2)
          return <p key={i} className="italic text-muted-foreground">{line.slice(1, -1)}</p>;
        if (line === "")
          return <div key={i} className="h-2" />;
        // Bold inline: **text**
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
  step: (typeof W8_STEPS)[0];
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

  return (
    <div className="flex items-start gap-3 py-1.5">
      <div className="mt-0.5 shrink-0">{icon}</div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
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
          {status.state === "skipped" && (
            <Badge variant="outline" className="text-xs">skipped</Badge>
          )}
          {status.cost != null && status.cost > 0 && (
            <span className="text-xs text-muted-foreground">${status.cost.toFixed(4)}</span>
          )}
          {status.duration_ms != null && (
            <span className="text-xs text-muted-foreground">
              {status.duration_ms > 1000
                ? `${(status.duration_ms / 1000).toFixed(1)}s`
                : `${status.duration_ms}ms`}
            </span>
          )}
        </div>
        {status.summary && status.state !== "pending" && (
          <p className="text-xs text-muted-foreground mt-0.5 truncate">{status.summary}</p>
        )}
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function PeerReviewPage() {
  const [pdfPath, setPdfPath] = useState("");
  const [budget, setBudget] = useState("3.0");
  const [running, setRunning] = useState(false);
  const [workflowId, setWorkflowId] = useState<string | null>(null);
  const [stepStatuses, setStepStatuses] = useState<Record<string, StepStatus>>({});
  const [markdownReport, setMarkdownReport] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [showReport, setShowReport] = useState(true);
  const [reportCopied, setReportCopied] = useState(false);
  const sseRef = useRef<EventSource | null>(null);

  const completedCount = Object.values(stepStatuses).filter(
    (s) => s.state === "completed" || s.state === "skipped",
  ).length;
  const progress = Math.round((completedCount / W8_STEPS.length) * 100);

  function stopSSE() {
    if (sseRef.current) {
      sseRef.current.close();
      sseRef.current = null;
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!pdfPath.trim()) return;

    setRunning(true);
    setError("");
    setMarkdownReport("");
    setStepStatuses({});
    setWorkflowId(null);
    stopSSE();

    try {
      // Create W8 workflow
      const res = await api.post<CreateWorkflowResponse>("/api/v1/workflows", {
        template: "W8",
        query: pdfPath.trim(),
        budget: parseFloat(budget) || 3.0,
        pdf_path: pdfPath.trim(),
      });

      const wid = res.workflow_id;
      setWorkflowId(wid);

      // Subscribe to SSE for step progress
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

          if (etype === "workflow.step_started") {
            const sid = data.step_id as string;
            setStepStatuses((prev) => ({
              ...prev,
              [sid]: { state: "running" },
            }));
          } else if (etype === "workflow.step_completed") {
            const sid = data.step_id as string;
            const payload = data.payload ?? {};
            setStepStatuses((prev) => ({
              ...prev,
              [sid]: {
                state: (payload.status as StepState) ?? "completed",
                summary: payload.summary as string | undefined,
                cost: payload.cost as number | undefined,
                duration_ms: payload.duration_ms as number | undefined,
              },
            }));
          } else if (etype === "workflow.completed") {
            stopSSE();
            // Fetch final result
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
        // SSE closed — try fetching result anyway
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
      }>(`/api/v1/workflows/${wid}`);

      const reportStep = result.step_results?.["REPORT"];
      const output = reportStep?.output as Record<string, unknown> | undefined;
      const md = output?.markdown_report as string | undefined;
      if (md) {
        setMarkdownReport(md);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch report");
    } finally {
      setRunning(false);
    }
  }

  function handleCopyReport() {
    if (!markdownReport) return;
    navigator.clipboard.writeText(markdownReport);
    setReportCopied(true);
    setTimeout(() => setReportCopied(false), 2000);
  }

  function handleDownloadReport() {
    if (!markdownReport) return;
    const blob = new Blob([markdownReport], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "peer_review_report.md";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="flex flex-col gap-6 p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3">
        <FileSearch className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold">W8 Peer Review</h1>
          <p className="text-sm text-muted-foreground">
            13-step systematic peer review pipeline — claim extraction, novelty assessment,
            citation validation, methodology review, RCMXT evidence grading
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Form + Pipeline Progress */}
        <div className="space-y-4">
          {/* Submission form */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Submit Paper</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="space-y-1.5">
                  <label htmlFor="pdf-path" className="text-sm font-medium">Paper Path (PDF or DOCX)</label>
                  <Input
                    id="pdf-path"
                    placeholder="/path/to/manuscript.pdf"
                    value={pdfPath}
                    onChange={(e) => setPdfPath(e.target.value)}
                    disabled={running}
                    className="font-mono text-xs"
                  />
                </div>
                <div className="space-y-1.5">
                  <label htmlFor="budget" className="text-sm font-medium">Budget (USD)</label>
                  <Input
                    id="budget"
                    type="number"
                    step="0.5"
                    min="0.5"
                    max="20"
                    value={budget}
                    onChange={(e) => setBudget(e.target.value)}
                    disabled={running}
                    className="w-28"
                  />
                </div>
                {error && (
                  <p className="text-xs text-red-500">{error}</p>
                )}
                <Button
                  type="submit"
                  disabled={running || !pdfPath.trim()}
                  className="w-full gap-2"
                >
                  {running ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Play className="h-4 w-4" />
                  )}
                  {running ? "Reviewing…" : "Start Review"}
                </Button>
              </form>
            </CardContent>
          </Card>

          {/* Pipeline Progress */}
          {(running || completedCount > 0) && (
            <Card>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Clock className="h-4 w-4" />
                    Pipeline Progress
                  </CardTitle>
                  <span className="text-sm text-muted-foreground">{progress}%</span>
                </div>
                <Progress value={progress} className="h-1.5 mt-1" />
              </CardHeader>
              <CardContent className="pt-0">
                <div className="divide-y divide-border/50">
                  {W8_STEPS.map((step, i) => (
                    <StepItem
                      key={step.id}
                      step={step}
                      status={stepStatuses[step.id] ?? { state: "pending" }}
                      index={i}
                    />
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Right: Report */}
        <div className="lg:col-span-2">
          {markdownReport ? (
            <Card className="h-full">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base flex items-center gap-2">
                    <FileSearch className="h-4 w-4" />
                    Peer Review Report
                  </CardTitle>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-1.5 text-xs"
                      onClick={handleCopyReport}
                    >
                      <Copy className="h-3 w-3" />
                      {reportCopied ? "Copied!" : "Copy"}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-1.5 text-xs"
                      onClick={handleDownloadReport}
                    >
                      <Download className="h-3 w-3" />
                      Download .md
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setShowReport(!showReport)}
                      aria-label={showReport ? "Collapse report" : "Expand report"}
                    >
                      {showReport ? (
                        <ChevronUp className="h-4 w-4" />
                      ) : (
                        <ChevronDown className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                </div>
                <Separator className="mt-2" />
              </CardHeader>
              {showReport && (
                <CardContent className="overflow-y-auto max-h-[75vh]">
                  <MarkdownSection text={markdownReport} />
                </CardContent>
              )}
            </Card>
          ) : (
            <Card className="flex items-center justify-center h-64 border-dashed">
              <div className="text-center text-muted-foreground">
                <FileSearch className="h-10 w-10 mx-auto mb-3 opacity-30" />
                <p className="text-sm">Review report will appear here</p>
                <p className="text-xs mt-1">Submit a paper to begin the analysis</p>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
