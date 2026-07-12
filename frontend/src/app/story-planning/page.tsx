"use client";

import React, { useState, useRef, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  BookOpen,
  Play,
  CheckCircle2,
  XCircle,
  Loader2,
  Copy,
  Download,
  AlertCircle,
  Pause,
  Sparkles,
  Target,
  Lightbulb,
  AlertTriangle,
} from "lucide-react";
import { api } from "@/lib/api-client";
import type { CreateWorkflowResponse, StoryFrame, StoryFrameSet } from "@/types/api";

// ─── W11 Pipeline Step Definitions ───────────────────────────────────────────

const W11_STEPS = [
  { id: "SCOPE", label: "Define Research Scope", type: "hc" as const },
  { id: "GENERATE_FRAMES", label: "Generate Narrative Frames", type: "llm" as const },
  { id: "HUMAN_CHECKPOINT", label: "Select Story Frame", type: "hc" as const },
  { id: "PRESENT", label: "Present Selected Frame", type: "code" as const },
];

type StepType = "hc" | "llm" | "code";
type StepState = "pending" | "running" | "completed" | "skipped" | "failed";

interface StepStatus {
  state: StepState;
  summary?: string;
  duration_ms?: number;
}

const STEP_TYPE_COLORS: Record<StepType, string> = {
  hc: "text-amber-500",
  llm: "text-emerald-500",
  code: "text-blue-500",
};

const STEP_TYPE_BADGE: Record<StepType, string> = {
  hc: "HC",
  llm: "LLM",
  code: "CODE",
};

const NARRATIVE_LABELS: Record<string, { label: string; color: string }> = {
  mechanism_discovery: { label: "Mechanism Discovery", color: "bg-blue-500/20 text-blue-400 border-blue-500/30" },
  paradigm_challenge: { label: "Paradigm Challenge", color: "bg-red-500/20 text-red-400 border-red-500/30" },
  clinical_implication: { label: "Clinical Implication", color: "bg-green-500/20 text-green-400 border-green-500/30" },
  field_bridge: { label: "Field Bridge", color: "bg-purple-500/20 text-purple-400 border-purple-500/30" },
  negative_reframe: { label: "Negative Reframe", color: "bg-amber-500/20 text-amber-400 border-amber-500/30" },
  method_breakthrough: { label: "Method Breakthrough", color: "bg-cyan-500/20 text-cyan-400 border-cyan-500/30" },
};

const TIER_OPTIONS = [
  { value: "nature_cell", label: "Top-tier (Nature / Science / Cell)" },
  { value: "specialty", label: "Specialty (field-specific journals)" },
  { value: "grant", label: "Grant proposal narrative" },
];

// ─── Step Progress Item ───────────────────────────────────────────────────────

function StepItem({
  step,
  status,
  index,
}: {
  step: (typeof W11_STEPS)[0];
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
    ) : (
      <div className="h-4 w-4 rounded-full border-2 border-muted-foreground/30" />
    );

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
            className={`text-[9px] px-1 py-0 h-4 shrink-0 ${STEP_TYPE_COLORS[step.type]}`}
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

// ─── Story Frame Card ─────────────────────────────────────────────────────────

function FrameCard({
  frame,
  isSelected,
  onSelect,
}: {
  frame: StoryFrame;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const narr = NARRATIVE_LABELS[frame.narrative_type] ?? {
    label: frame.narrative_type,
    color: "bg-muted text-muted-foreground",
  };

  return (
    <Card
      className={`cursor-pointer transition-all hover:shadow-md ${
        isSelected
          ? "border-primary ring-2 ring-primary/30"
          : "border-border hover:border-primary/50"
      }`}
      onClick={onSelect}
    >
      <CardContent className="pt-4 space-y-3">
        {/* Header: narrative type + impact score */}
        <div className="flex items-center justify-between gap-2">
          <Badge variant="outline" className={`text-[10px] ${narr.color}`}>
            {narr.label}
          </Badge>
          <div className="flex items-center gap-1">
            <Target className="h-3 w-3 text-muted-foreground" />
            <span className="text-xs font-mono text-muted-foreground">
              {(frame.impact_score * 100).toFixed(0)}%
            </span>
          </div>
        </div>

        {/* Hook */}
        <div>
          <div className="flex items-center gap-1.5 mb-1">
            <Sparkles className="h-3 w-3 text-amber-400" />
            <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              Hook
            </span>
          </div>
          <p className="text-sm leading-snug italic">&ldquo;{frame.hook}&rdquo;</p>
        </div>

        {/* Core Claim */}
        <div>
          <div className="flex items-center gap-1.5 mb-1">
            <Lightbulb className="h-3 w-3 text-emerald-400" />
            <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              Core Claim
            </span>
          </div>
          <p className="text-sm">{frame.core_claim}</p>
        </div>

        {/* Central Tension */}
        <div>
          <div className="flex items-center gap-1.5 mb-1">
            <AlertTriangle className="h-3 w-3 text-orange-400" />
            <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              Central Tension
            </span>
          </div>
          <p className="text-xs text-muted-foreground">{frame.central_tension}</p>
        </div>

        {/* Frame ID + selection indicator */}
        <div className="flex items-center justify-between pt-1 border-t border-border/50">
          <span className="text-[10px] font-mono text-muted-foreground">{frame.frame_id}</span>
          {isSelected && (
            <Badge className="bg-primary text-primary-foreground text-[10px]">Selected</Badge>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Selected Frame Detail ────────────────────────────────────────────────────

function FrameDetail({ frame }: { frame: StoryFrame }) {
  const narr = NARRATIVE_LABELS[frame.narrative_type] ?? {
    label: frame.narrative_type,
    color: "bg-muted text-muted-foreground",
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        <Badge variant="outline" className={narr.color}>
          {narr.label}
        </Badge>
        <Badge variant="outline" className="text-xs">
          Impact: {(frame.impact_score * 100).toFixed(0)}%
        </Badge>
        <Badge variant="outline" className="text-xs">
          Tier: {frame.target_tier}
        </Badge>
      </div>

      <div>
        <h3 className="text-sm font-semibold mb-1">Hook</h3>
        <p className="text-sm italic text-primary">&ldquo;{frame.hook}&rdquo;</p>
      </div>

      <div>
        <h3 className="text-sm font-semibold mb-1">Core Claim</h3>
        <p className="text-sm">{frame.core_claim}</p>
      </div>

      <div>
        <h3 className="text-sm font-semibold mb-1">Central Tension</h3>
        <p className="text-sm text-muted-foreground">{frame.central_tension}</p>
      </div>

      <div>
        <h3 className="text-sm font-semibold mb-1">Novelty Rationale</h3>
        <p className="text-sm text-muted-foreground">{frame.novelty_rationale}</p>
      </div>

      {frame.supporting_findings.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold mb-1">Supporting Findings</h3>
          <ul className="list-disc ml-4 space-y-0.5">
            {frame.supporting_findings.map((f, i) => (
              <li key={i} className="text-sm text-muted-foreground">{f}</li>
            ))}
          </ul>
        </div>
      )}

      {frame.figure_sequence.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold mb-1">Figure Sequence</h3>
          <ol className="list-decimal ml-4 space-y-0.5">
            {frame.figure_sequence.map((f, i) => (
              <li key={i} className="text-sm text-muted-foreground">{f}</li>
            ))}
          </ol>
        </div>
      )}

      {frame.blind_spots.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold mb-1">Blind Spots</h3>
          <ul className="list-disc ml-4 space-y-0.5">
            {frame.blind_spots.map((b, i) => (
              <li key={i} className="text-sm text-amber-400/80">{b}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function StoryPlanningPage() {
  const [query, setQuery] = useState("");
  const [tier, setTier] = useState("specialty");
  const [running, setRunning] = useState(false);
  const [workflowId, setWorkflowId] = useState<string | null>(null);
  const [stepStatuses, setStepStatuses] = useState<Record<string, StepStatus>>({});
  const [error, setError] = useState("");
  const [phase, setPhase] = useState<"idle" | "awaiting_scope" | "awaiting_selection" | "complete">("idle");
  const [frames, setFrames] = useState<StoryFrame[]>([]);
  const [frameGenerationMode, setFrameGenerationMode] = useState<StoryFrameSet["generation_mode"]>("llm");
  const [frameFallbackReason, setFrameFallbackReason] = useState<string | null>(null);
  const [selectedFrameId, setSelectedFrameId] = useState<string | null>(null);
  const [selectedFrame, setSelectedFrame] = useState<StoryFrame | null>(null);
  const [reportCopied, setReportCopied] = useState(false);
  const [resuming, setResuming] = useState(false);
  const sseRef = useRef<EventSource | null>(null);

  const completedCount = Object.values(stepStatuses).filter(
    (s) => s.state === "completed" || s.state === "skipped",
  ).length;
  const progress = Math.round((completedCount / W11_STEPS.length) * 100);

  function stopSSE() {
    if (sseRef.current) {
      sseRef.current.close();
      sseRef.current = null;
    }
  }

  const fetchFrames = useCallback(async (wid: string) => {
    try {
      const result = await api.get<{
        session_manifest?: Record<string, unknown>;
      }>(`/api/v1/workflows/${wid}`);

      const frameOptions = result.session_manifest?.["frame_options"] as StoryFrameSet | undefined;
      if (frameOptions?.frames) {
        setFrames(frameOptions.frames);
        setFrameGenerationMode(frameOptions.generation_mode ?? "llm");
        setFrameFallbackReason(frameOptions.fallback_reason ?? null);
      }
      const selectionError = result.session_manifest?.["selection_error"];
      if (typeof selectionError === "string" && selectionError) {
        setError(selectionError);
      } else {
        setError("");
      }
    } catch {
      // Frames may not be ready yet
    }
  }, []);

  const fetchSelectedFrame = useCallback(async (wid: string) => {
    try {
      const result = await api.get<{
        session_manifest?: Record<string, unknown>;
      }>(`/api/v1/workflows/${wid}`);

      const frame = result.session_manifest?.["selected_story_frame"] as StoryFrame | undefined;
      if (frame) {
        setSelectedFrame(frame);
        setSelectedFrameId(frame.frame_id);
        setPhase("complete");
      }

      const frameOptions = result.session_manifest?.["frame_options"] as StoryFrameSet | undefined;
      if (frameOptions?.frames && frames.length === 0) {
        setFrames(frameOptions.frames);
      }
      if (frameOptions) {
        setFrameGenerationMode(frameOptions.generation_mode ?? "llm");
        setFrameFallbackReason(frameOptions.fallback_reason ?? null);
      }
      const selectionError = result.session_manifest?.["selection_error"];
      if (typeof selectionError === "string" && selectionError) {
        setError(selectionError);
      }
    } catch {
      // ignore
    } finally {
      setRunning(false);
    }
  }, [frames.length]);

  const connectSSE = useCallback((wid: string) => {
    stopSSE();
    const apiKey = typeof window !== "undefined" ? localStorage.getItem("bioteam_api_key") : null;

    const connect = async () => {
      let sseUrl = `/api/v1/sse/workflow/${wid}`;
      if (apiKey) {
        try {
          const streamToken = await api.post<{ token: string }>("/api/v1/auth/stream-token", {
            path: `/api/v1/sse/workflow/${wid}`,
          });
          sseUrl += `?token=${encodeURIComponent(streamToken.token)}`;
        } catch {
          // Continue without token in dev mode
        }
      }
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
            // Determine which HC based on step context
            const sid = data.step_id as string;
            if (sid === "SCOPE") {
              setPhase("awaiting_scope");
            } else if (sid === "HUMAN_CHECKPOINT") {
              setPhase("awaiting_selection");
              // Fetch frames from workflow state
              fetchFrames(wid);
            }
          } else if (etype === "workflow.paused") {
            const pausedAt = data.payload?.paused_at as string | undefined;
            if (pausedAt === "SCOPE") {
              setPhase("awaiting_scope");
            } else if (pausedAt === "HUMAN_CHECKPOINT") {
              setPhase("awaiting_selection");
              fetchFrames(wid);
            }
            setRunning(false);
          } else if (etype === "workflow.completed") {
            stopSSE();
            setPhase("complete");
            fetchSelectedFrame(wid);
            setRunning(false);
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
        // Try to fetch final state
        fetchSelectedFrame(wid);
      };
    };

    connect();
  }, [fetchFrames, fetchSelectedFrame]);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!query.trim()) return;

    setRunning(true);
    setPhase("idle");
    setError("");
    setFrames([]);
    setFrameGenerationMode("llm");
    setFrameFallbackReason(null);
    setSelectedFrameId(null);
    setSelectedFrame(null);
    setStepStatuses({});
    setWorkflowId(null);
    stopSSE();

    try {
      const res = await api.post<CreateWorkflowResponse>("/api/v1/workflows", {
        template: "W11",
        query: query.trim(),
        budget: 2.0,
      });

      const wid = res.workflow_id;
      setWorkflowId(wid);
      connectSSE(wid);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setRunning(false);
    }
  }

  async function handleResumeScope() {
    if (!workflowId || resuming) return;
    setResuming(true);
    setError("");
    try {
      // Inject tier as a note before resuming
      await api.post(`/api/v1/workflows/${workflowId}/intervene`, {
        action: "inject_note",
        note: `target_tier: ${tier}`,
        note_action: "FREE_TEXT",
      });
      await api.post(`/api/v1/workflows/${workflowId}/intervene`, { action: "resume" });
      setPhase("idle");
      setRunning(true);
      connectSSE(workflowId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to resume workflow");
    } finally {
      setResuming(false);
    }
  }

  async function handleSelectFrame() {
    if (!workflowId || !selectedFrameId || resuming) return;
    setResuming(true);
    setError("");
    try {
      // Inject selection as a note
      await api.post(`/api/v1/workflows/${workflowId}/intervene`, {
        action: "inject_note",
        note: `selected_frame_id: ${selectedFrameId}`,
        note_action: "FREE_TEXT",
      });
      await api.post(`/api/v1/workflows/${workflowId}/intervene`, { action: "resume" });
      setPhase("idle");
      setRunning(true);
      connectSSE(workflowId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to select frame");
    } finally {
      setResuming(false);
    }
  }

  function handleCopy() {
    if (!selectedFrame) return;
    const text = [
      `# Story Frame: ${selectedFrame.frame_id}`,
      `## Narrative Type: ${NARRATIVE_LABELS[selectedFrame.narrative_type]?.label ?? selectedFrame.narrative_type}`,
      `## Hook\n${selectedFrame.hook}`,
      `## Core Claim\n${selectedFrame.core_claim}`,
      `## Central Tension\n${selectedFrame.central_tension}`,
      `## Novelty Rationale\n${selectedFrame.novelty_rationale}`,
      `## Supporting Findings\n${selectedFrame.supporting_findings.map((f) => `- ${f}`).join("\n")}`,
      `## Figure Sequence\n${selectedFrame.figure_sequence.map((f, i) => `${i + 1}. ${f}`).join("\n")}`,
      `## Blind Spots\n${selectedFrame.blind_spots.map((b) => `- ${b}`).join("\n")}`,
      `\nImpact Score: ${(selectedFrame.impact_score * 100).toFixed(0)}% | Target Tier: ${selectedFrame.target_tier}`,
    ].join("\n\n");
    navigator.clipboard.writeText(text);
    setReportCopied(true);
    setTimeout(() => setReportCopied(false), 2000);
  }

  function handleDownload() {
    if (!selectedFrame) return;
    const text = JSON.stringify(selectedFrame, null, 2);
    const blob = new Blob([text], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `story_frame_${selectedFrame.frame_id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="flex flex-col gap-6 p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3">
        <BookOpen className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold">Story Frames</h1>
          <p className="text-sm text-muted-foreground">
            Generate 3-5 narrative frames for your research paper and choose the
            strongest angle before drafting
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* ── Left column: Form + Pipeline Progress ── */}
        <div className="space-y-4">
          {/* Input form */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Research Context</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-3">
                <div className="space-y-1">
                  <label htmlFor="research-query" className="text-sm font-medium">
                    Research Question
                  </label>
                  <textarea
                    id="research-query"
                    placeholder="e.g. We found that gene X is upregulated in condition Y, contradicting the established role of X as a suppressor..."
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    disabled={running}
                    className="flex min-h-[100px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                    rows={4}
                  />
                </div>
                <div className="space-y-1">
                  <label htmlFor="journal-tier" className="text-sm font-medium">
                    Target Journal Tier
                  </label>
                  <select
                    id="journal-tier"
                    value={tier}
                    onChange={(e) => setTier(e.target.value)}
                    disabled={running}
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {TIER_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>
                <Button
                  type="submit"
                  disabled={running || !query.trim()}
                  className="w-full gap-2"
                >
                  {running ? (
                    <><Loader2 className="h-4 w-4 animate-spin" /> Running...</>
                  ) : (
                    <><Play className="h-4 w-4" /> Generate Frames</>
                  )}
                </Button>
              </form>
            </CardContent>
          </Card>

          {/* SCOPE checkpoint notification */}
          {phase === "awaiting_scope" && (
            <Card className="border-amber-500/50 bg-amber-500/10">
              <CardContent className="pt-4">
                <div className="flex items-start gap-2">
                  <Pause className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-amber-700 dark:text-amber-400">
                      Human Checkpoint — Scope Review
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Confirm your research question and journal tier, then
                      approve to generate narrative frames.
                    </p>
                  </div>
                </div>
                <Button
                  size="sm"
                  className="mt-3 w-full gap-2 bg-amber-500 hover:bg-amber-600 text-white"
                  onClick={handleResumeScope}
                  disabled={resuming}
                >
                  {resuming ? (
                    <><Loader2 className="h-3.5 w-3.5 animate-spin" /> Resuming...</>
                  ) : (
                    <><Play className="h-3.5 w-3.5" /> Approve &amp; Generate</>
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
                  {W11_STEPS.map((step, idx) => (
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
            <span className="text-emerald-500 font-medium ml-2">LLM</span> AI Generation
            <span className="text-blue-500 font-medium ml-2">CODE</span> Processing
          </div>
        </div>

        {/* ── Right column (2/3): Frame Selection or Detail ── */}
        <div className="lg:col-span-2">
          {/* Frame selection panel */}
          {phase === "awaiting_selection" && frames.length > 0 && (
            <div className="space-y-4">
              {frameGenerationMode === "synthetic_fallback" && (
                <Card className="border-amber-500/50 bg-amber-500/10">
                  <CardContent className="pt-4 flex items-start gap-2">
                    <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
                    <div className="space-y-1">
                      <p className="text-sm font-medium text-amber-700 dark:text-amber-400">
                        Synthetic fallback frames
                      </p>
                      <p className="text-xs text-muted-foreground">
                        These story frames were generated without the normal LLM planning step.
                        Treat them as placeholders until you review them carefully.
                      </p>
                      {frameFallbackReason && (
                        <p className="text-xs text-muted-foreground">
                          Reason: {frameFallbackReason}
                        </p>
                      )}
                    </div>
                  </CardContent>
                </Card>
              )}
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">Select a Narrative Frame</h2>
                <Button
                  onClick={handleSelectFrame}
                  disabled={!selectedFrameId || resuming}
                  className="gap-2"
                >
                  {resuming ? (
                    <><Loader2 className="h-4 w-4 animate-spin" /> Confirming...</>
                  ) : (
                    <><CheckCircle2 className="h-4 w-4" /> Confirm Selection</>
                  )}
                </Button>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {frames.map((frame) => (
                  <FrameCard
                    key={frame.frame_id}
                    frame={frame}
                    isSelected={selectedFrameId === frame.frame_id}
                    onSelect={() => setSelectedFrameId(frame.frame_id)}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Completed: show selected frame detail */}
          {phase === "complete" && selectedFrame && (
            <Card className="h-full min-h-[400px]">
              <CardHeader className="pb-2">
                {selectedFrame.provenance === "synthetic_fallback" && (
                  <div className="mb-3 rounded-md border border-amber-500/50 bg-amber-500/10 px-3 py-2 text-xs text-muted-foreground">
                    Selected frame came from the synthetic fallback path, not the standard LLM frame generator.
                    {frameFallbackReason ? ` Reason: ${frameFallbackReason}` : ""}
                  </div>
                )}
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">
                    Selected Frame: {selectedFrame.frame_id}
                  </CardTitle>
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
                      .json
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <FrameDetail frame={selectedFrame} />
              </CardContent>
            </Card>
          )}

          {/* Default: empty state */}
          {phase !== "awaiting_selection" && phase !== "complete" && (
            <Card className="h-full min-h-[400px]">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Narrative Frames</CardTitle>
              </CardHeader>
              <CardContent>
                {running ? (
                  <div className="flex flex-col items-center justify-center py-16 gap-3 text-muted-foreground">
                    <Loader2 className="h-8 w-8 animate-spin" />
                    <p className="text-sm">Generating narrative frames...</p>
                    {workflowId && (
                      <p className="text-xs font-mono opacity-60">
                        {workflowId.slice(0, 12)}...
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center py-16 gap-3 text-muted-foreground">
                    <BookOpen className="h-10 w-10 opacity-20" />
                    <p className="text-sm">
                      Enter your research context to generate narrative frames.
                    </p>
                    <div className="text-xs text-center max-w-sm space-y-1 opacity-70">
                      <p>W11 generates 3-5 different story angles for your paper:</p>
                      <p className="italic">
                        mechanism discovery, paradigm challenge, clinical implication,
                        field bridge, negative reframe
                      </p>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
