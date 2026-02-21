"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Pause,
  Play,
  XCircle,
  MessageSquarePlus,
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  Loader2,
  Clock,
  AlertCircle,
} from "lucide-react";
import { useAppStore } from "@/stores/app-store";
import { api } from "@/lib/api-client";
import type {
  InterveneResponse,
  NoteAction,
  WorkflowStatus,
  StepCheckpoint,
  StepHistoryEntry,
  RCMXTScore,
} from "@/types/api";

const W1_STEP_LABELS: Record<string, string> = {
  SCOPE: "Scope Definition",
  SEARCH: "Literature Search",
  SCREEN: "Paper Screening",
  EXTRACT: "Data Extraction",
  NEGATIVE_CHECK: "Negative Results Check",
  SYNTHESIZE: "Synthesis (Human Checkpoint)",
  CITATION_CHECK: "Citation Validation",
  RCMXT_SCORE: "Evidence Scoring (RCMXT)",
  NOVELTY_CHECK: "Novelty Assessment",
  REPORT: "Final Report",
};

const W1_ALL_STEPS = [
  "SCOPE", "SEARCH", "SCREEN", "EXTRACT", "NEGATIVE_CHECK", "SYNTHESIZE",
  "CITATION_CHECK", "RCMXT_SCORE", "NOVELTY_CHECK", "REPORT",
];

function stepStatusIcon(stepId: string, workflow: WorkflowStatus) {
  const completed = workflow.step_history.some((s) => s.step_id === stepId);
  const isCurrent = workflow.current_step === stepId;
  const isRunning = workflow.state === "RUNNING" && isCurrent;

  if (completed && !isCurrent) return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />;
  if (isRunning) return <Loader2 className="h-3.5 w-3.5 text-blue-500 animate-spin shrink-0" />;
  if (isCurrent && workflow.state === "WAITING_HUMAN") return <Clock className="h-3.5 w-3.5 text-amber-500 shrink-0" />;
  if (workflow.state === "FAILED" && isCurrent) return <AlertCircle className="h-3.5 w-3.5 text-red-500 shrink-0" />;
  return <span className="h-3.5 w-3.5 rounded-full border border-border shrink-0 inline-block" />;
}

export function WorkflowDetailSheet() {
  const selectedId = useAppStore((s) => s.selectedWorkflowId);
  const setSelected = useAppStore((s) => s.setSelectedWorkflowId);
  const [workflow, setWorkflow] = useState<WorkflowStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [note, setNote] = useState("");
  const [noteAction, setNoteAction] = useState<NoteAction>("FREE_TEXT");
  const [intervening, setIntervening] = useState(false);
  const [expandedSteps, setExpandedSteps] = useState<Set<string>>(new Set());

  const fetchWorkflow = useCallback(async () => {
    if (!selectedId) return;
    try {
      setLoading(true);
      const data = await api.get<WorkflowStatus>(`/api/v1/workflows/${selectedId}`);
      setWorkflow(data);
    } catch {
      // handled
    } finally {
      setLoading(false);
    }
  }, [selectedId]);

  // Initial fetch
  useEffect(() => {
    if (selectedId) {
      fetchWorkflow();
    } else {
      setWorkflow(null);
      setExpandedSteps(new Set());
    }
  }, [selectedId, fetchWorkflow]);

  // Auto-refresh while workflow is active
  useEffect(() => {
    if (!selectedId || !workflow) return;
    const activeStates = ["RUNNING", "PENDING"];
    if (!activeStates.includes(workflow.state)) return;

    const interval = setInterval(fetchWorkflow, 3000);
    return () => clearInterval(interval);
  }, [selectedId, workflow?.state, fetchWorkflow]);

  const doIntervene = async (action: string) => {
    if (!selectedId) return;
    setIntervening(true);
    try {
      await api.post<InterveneResponse>(
        `/api/v1/workflows/${selectedId}/intervene`,
        {
          action,
          ...(action === "inject_note" ? { note, note_action: noteAction } : {}),
        },
      );
      if (action === "inject_note") setNote("");
      // Refresh after intervention
      await fetchWorkflow();
    } catch {
      // error handled by API client
    } finally {
      setIntervening(false);
    }
  };

  const toggleStep = (stepId: string) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev);
      if (next.has(stepId)) next.delete(stepId);
      else next.add(stepId);
      return next;
    });
  };

  const budgetUsed = workflow
    ? workflow.budget_total - workflow.budget_remaining
    : 0;
  const budgetPct = workflow && workflow.budget_total > 0
    ? Math.round((budgetUsed / workflow.budget_total) * 100)
    : 0;

  return (
    <Sheet open={!!selectedId} onOpenChange={(open) => !open && setSelected(null)}>
      <SheetContent className="w-[500px] overflow-y-auto sm:max-w-[500px] p-0">
        <div className="p-6 pb-0">
          <SheetHeader>
            <SheetTitle>
              Workflow {workflow?.template ?? ""}
            </SheetTitle>
            <SheetDescription>
              {workflow
                ? `${workflow.template} pipeline details and controls (${workflow.state})`
                : "Loading workflow details"}
            </SheetDescription>
          </SheetHeader>
        </div>

        {loading && !workflow && (
          <p className="px-6 py-4 text-sm text-muted-foreground">Loading...</p>
        )}

        {workflow && (
          <ScrollArea className="h-[calc(100vh-120px)]">
            <div className="space-y-4 p-6 pt-4">
              {/* State badge + ID */}
              <div className="flex items-center gap-2">
                <StateBadge state={workflow.state} />
                <span className="font-mono text-xs text-muted-foreground truncate">
                  {workflow.id}
                </span>
                {(workflow.state === "RUNNING" || workflow.state === "PENDING") && (
                  <Loader2 className="h-3 w-3 animate-spin text-muted-foreground ml-auto" />
                )}
              </div>

              {/* Budget */}
              <div className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span className="text-muted-foreground">Budget</span>
                  <span className="font-mono">
                    ${budgetUsed.toFixed(2)} / ${workflow.budget_total.toFixed(2)}
                  </span>
                </div>
                <Progress value={budgetPct} className="h-2" />
              </div>

              <Separator />

              {/* Pipeline Steps */}
              <div>
                <p className="mb-2 text-xs font-medium text-muted-foreground">
                  Pipeline Steps ({workflow.step_history.length}/{W1_ALL_STEPS.length})
                </p>
                <div className="space-y-0.5">
                  {W1_ALL_STEPS.map((stepId) => {
                    const historyEntry = workflow.step_history.find(
                      (s) => s.step_id === stepId
                    );
                    const hasData = historyEntry && historyEntry.result_data;
                    const isExpanded = expandedSteps.has(stepId);

                    return (
                      <div key={stepId}>
                        <button
                          className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-xs hover:bg-accent text-left"
                          onClick={() => hasData && toggleStep(stepId)}
                          disabled={!hasData}
                          aria-expanded={isExpanded}
                          aria-label={`${W1_STEP_LABELS[stepId] ?? stepId}: ${historyEntry ? "completed" : "pending"}`}
                        >
                          {stepStatusIcon(stepId, workflow)}
                          <span className="font-medium flex-1">
                            {W1_STEP_LABELS[stepId] ?? stepId}
                          </span>
                          {historyEntry?.completed_at && (
                            <span className="text-muted-foreground text-[10px]">
                              {formatTime(historyEntry.completed_at as string)}
                            </span>
                          )}
                          {hasData && (
                            isExpanded
                              ? <ChevronDown className="h-3 w-3 text-muted-foreground" />
                              : <ChevronRight className="h-3 w-3 text-muted-foreground" />
                          )}
                        </button>

                        {/* Expanded step result */}
                        {isExpanded && hasData && (
                          <StepResultPanel data={historyEntry.result_data as Record<string, unknown>} stepId={stepId} />
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* WAITING_HUMAN banner */}
              {workflow.state === "WAITING_HUMAN" && (
                <>
                  <Separator />
                  <div className="rounded-md border border-amber-500/50 bg-amber-500/10 p-3">
                    <p className="text-xs font-medium text-amber-500 mb-1">
                      Human Review Required
                    </p>
                    <p className="text-xs text-muted-foreground">
                      The synthesis step is complete. Review the results above, then click
                      Resume to continue with citation validation, evidence scoring, novelty
                      check, and final report.
                    </p>
                  </div>
                </>
              )}

              {/* Loop counts */}
              {Object.keys(workflow.loop_count).length > 0 && (
                <>
                  <Separator />
                  <div>
                    <p className="mb-1 text-xs font-medium text-muted-foreground">
                      Loop Counts
                    </p>
                    <div className="space-y-0.5 text-xs">
                      {Object.entries(workflow.loop_count).map(([k, v]) => (
                        <div key={k} className="flex justify-between">
                          <span>{k}</span>
                          <span className="font-mono">{v}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              )}

              {/* RCMXT Evidence Scores */}
              {workflow.rcmxt_scores && workflow.rcmxt_scores.length > 0 && (
                <>
                  <Separator />
                  <RCMXTScoreTable scores={workflow.rcmxt_scores} />
                </>
              )}

              {/* Citation Report */}
              {workflow.citation_report && workflow.citation_report.total_citations > 0 && (
                <>
                  <Separator />
                  <div>
                    <p className="mb-1.5 text-xs font-medium text-muted-foreground">
                      Citation Validation
                    </p>
                    <div className="space-y-1 text-xs">
                      <div className="flex justify-between">
                        <span>Total citations</span>
                        <span className="font-mono">{workflow.citation_report.total_citations}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Verified</span>
                        <span className="font-mono text-emerald-500">{workflow.citation_report.verified}</span>
                      </div>
                      {workflow.citation_report.unverified > 0 && (
                        <div className="flex justify-between">
                          <span>Unverified</span>
                          <span className="font-mono text-amber-500">{workflow.citation_report.unverified}</span>
                        </div>
                      )}
                      <div className="flex justify-between">
                        <span>Verification rate</span>
                        <span className="font-mono">
                          {(workflow.citation_report.verification_rate * 100).toFixed(0)}%
                        </span>
                      </div>
                      {workflow.citation_report.is_clean && (
                        <Badge variant="default" className="text-[10px] mt-1">Clean</Badge>
                      )}
                    </div>
                  </div>
                </>
              )}

              <Separator />

              {/* Intervention Controls */}
              <div>
                <p className="mb-2 text-xs font-medium text-muted-foreground">
                  Interventions
                </p>
                <div className="flex gap-2" role="group" aria-label="Workflow intervention actions">
                  {workflow.state === "WAITING_HUMAN" && (
                    <Button
                      size="sm"
                      variant="default"
                      disabled={intervening}
                      onClick={() => doIntervene("resume")}
                      aria-label={`Approve and resume workflow ${workflow.template}`}
                    >
                      <Play className="mr-1 h-3 w-3" aria-hidden="true" /> Approve & Resume
                    </Button>
                  )}
                  {workflow.state === "RUNNING" && (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={intervening}
                      onClick={() => doIntervene("pause")}
                      aria-label={`Pause workflow ${workflow.template}`}
                    >
                      <Pause className="mr-1 h-3 w-3" aria-hidden="true" /> Pause
                    </Button>
                  )}
                  {workflow.state === "PAUSED" && (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={intervening}
                      onClick={() => doIntervene("resume")}
                      aria-label={`Resume workflow ${workflow.template}`}
                    >
                      <Play className="mr-1 h-3 w-3" aria-hidden="true" /> Resume
                    </Button>
                  )}
                  {["PENDING", "RUNNING", "PAUSED", "WAITING_HUMAN"].includes(workflow.state) && (
                    <Button
                      size="sm"
                      variant="destructive"
                      disabled={intervening}
                      onClick={() => doIntervene("cancel")}
                      aria-label={`Cancel workflow ${workflow.template}`}
                    >
                      <XCircle className="mr-1 h-3 w-3" aria-hidden="true" /> Cancel
                    </Button>
                  )}
                </div>

                {/* Inject Note */}
                {["RUNNING", "PAUSED", "WAITING_HUMAN"].includes(workflow.state) && (
                  <div className="mt-3 space-y-2">
                    <label htmlFor="note-action-select" className="sr-only">Note action type</label>
                    <Select value={noteAction} onValueChange={(v) => setNoteAction(v as NoteAction)}>
                      <SelectTrigger className="h-8 text-xs" id="note-action-select" aria-label="Note action type">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="FREE_TEXT">Free Text</SelectItem>
                        <SelectItem value="ADD_PAPER">Add Paper</SelectItem>
                        <SelectItem value="EXCLUDE_PAPER">Exclude Paper</SelectItem>
                        <SelectItem value="MODIFY_QUERY">Modify Query</SelectItem>
                        <SelectItem value="EDIT_TEXT">Edit Text</SelectItem>
                      </SelectContent>
                    </Select>
                    <label htmlFor="workflow-note-input" className="sr-only">Workflow note</label>
                    <Textarea
                      id="workflow-note-input"
                      placeholder="Enter note for workflow..."
                      className="min-h-[60px] text-xs"
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      aria-label="Enter note for workflow"
                    />
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={intervening || !note.trim()}
                      onClick={() => doIntervene("inject_note")}
                      aria-label="Inject note into workflow"
                    >
                      <MessageSquarePlus className="mr-1 h-3 w-3" aria-hidden="true" /> Inject Note
                    </Button>
                  </div>
                )}
              </div>
            </div>
          </ScrollArea>
        )}
      </SheetContent>
    </Sheet>
  );
}

function StateBadge({ state }: { state: string }) {
  const variants: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
    RUNNING: "default",
    COMPLETED: "default",
    PENDING: "secondary",
    PAUSED: "outline",
    WAITING_HUMAN: "outline",
    FAILED: "destructive",
    CANCELLED: "secondary",
    OVER_BUDGET: "destructive",
  };
  return <Badge variant={variants[state] ?? "secondary"} className="text-xs">{state}</Badge>;
}

function RCMXTScoreTable({ scores }: { scores: RCMXTScore[] }) {
  return (
    <div>
      <p className="mb-1.5 text-xs font-medium text-muted-foreground">
        Evidence Quality (RCMXT)
      </p>
      <div className="overflow-x-auto rounded border border-border">
        <table className="w-full text-[11px]">
          <thead>
            <tr className="border-b border-border bg-accent/50">
              <th className="px-2 py-1 text-left font-medium text-muted-foreground">Claim</th>
              <th className="px-1.5 py-1 text-center font-medium text-muted-foreground" title="Reproducibility">R</th>
              <th className="px-1.5 py-1 text-center font-medium text-muted-foreground" title="Condition Specificity">C</th>
              <th className="px-1.5 py-1 text-center font-medium text-muted-foreground" title="Methodology">M</th>
              <th className="px-1.5 py-1 text-center font-medium text-muted-foreground" title="Cross-Omics">X</th>
              <th className="px-1.5 py-1 text-center font-medium text-muted-foreground" title="Temporal">T</th>
              <th className="px-1.5 py-1 text-center font-medium text-muted-foreground">Score</th>
            </tr>
          </thead>
          <tbody>
            {scores.map((s, i) => (
              <tr key={i} className="border-b border-border last:border-0">
                <td className="px-2 py-1 max-w-[180px] truncate" title={s.claim}>
                  {s.claim}
                </td>
                <td className="px-1.5 py-1 text-center font-mono">{s.R.toFixed(2)}</td>
                <td className="px-1.5 py-1 text-center font-mono">{s.C.toFixed(2)}</td>
                <td className="px-1.5 py-1 text-center font-mono">{s.M.toFixed(2)}</td>
                <td className="px-1.5 py-1 text-center font-mono text-muted-foreground">
                  {s.X !== null ? s.X.toFixed(2) : "—"}
                </td>
                <td className="px-1.5 py-1 text-center font-mono">{s.T.toFixed(2)}</td>
                <td className="px-1.5 py-1 text-center font-mono font-medium">
                  {s.composite !== null ? s.composite.toFixed(2) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-1 text-[10px] text-muted-foreground">
        v0.1-heuristic | R=Reproducibility C=Condition M=Methodology X=Cross-Omics T=Temporal
      </p>
    </div>
  );
}

function StepResultPanel({ data, stepId }: { data: Record<string, unknown>; stepId: string }) {
  return (
    <div className="ml-6 mb-2 rounded border border-border bg-accent/30 p-2 text-xs space-y-1.5">
      {Object.entries(data).map(([key, value]) => {
        if (value === null || value === undefined) return null;
        const displayKey = key.replace(/_/g, " ");

        if (typeof value === "string" && value.length > 100) {
          return (
            <div key={key}>
              <span className="font-medium text-muted-foreground capitalize">{displayKey}:</span>
              <p className="mt-0.5 whitespace-pre-wrap text-[11px] leading-relaxed max-h-[200px] overflow-y-auto">
                {value}
              </p>
            </div>
          );
        }

        if (Array.isArray(value)) {
          return (
            <div key={key}>
              <span className="font-medium text-muted-foreground capitalize">
                {displayKey} ({value.length}):
              </span>
              <div className="mt-0.5 space-y-0.5">
                {value.slice(0, 10).map((item, i) => (
                  <div key={i} className="text-[11px] pl-2 border-l border-border">
                    {typeof item === "object" ? JSON.stringify(item).slice(0, 200) : String(item)}
                  </div>
                ))}
                {value.length > 10 && (
                  <span className="text-muted-foreground text-[10px]">
                    ...and {value.length - 10} more
                  </span>
                )}
              </div>
            </div>
          );
        }

        if (typeof value === "object") {
          return (
            <div key={key}>
              <span className="font-medium text-muted-foreground capitalize">{displayKey}:</span>
              <pre className="mt-0.5 text-[11px] whitespace-pre-wrap max-h-[150px] overflow-y-auto">
                {JSON.stringify(value, null, 2)}
              </pre>
            </div>
          );
        }

        return (
          <div key={key} className="flex gap-2">
            <span className="font-medium text-muted-foreground capitalize shrink-0">{displayKey}:</span>
            <span>{String(value)}</span>
          </div>
        );
      })}
    </div>
  );
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return "";
  }
}
