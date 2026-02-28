"use client";

import { useCallback, useEffect, useRef, useState } from "react";
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
  RefreshCw,
  SkipForward,
  DollarSign,
  Navigation,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { useAppStore } from "@/stores/app-store";
import { api } from "@/lib/api-client";
import { WorkflowPipelineGraph } from "./workflow-pipeline-graph";
import { RCMXTScoreTable } from "./rcmxt-score-display";
import { StepResultPanel } from "./step-result-panel";
import type {
  InterveneResponse,
  NoteAction,
  WorkflowStatus,
  ResumeResponse,
  StepActionResponse,
} from "@/types/api";

const STEP_LABELS: Record<string, string> = {
  // W1 steps
  SCOPE: "Scope Definition",
  SEARCH: "Literature Search",
  SCREEN: "Paper Screening",
  EXTRACT: "Data Extraction",
  NEGATIVE_CHECK: "Negative Results Check",
  SYNTHESIZE: "Synthesis (Human Checkpoint)",
  CONTRADICTION_CHECK: "Contradiction Detection",
  CITATION_CHECK: "Citation Validation",
  RCMXT_SCORE: "Evidence Scoring (RCMXT)",
  NOVELTY_CHECK: "Novelty Assessment",
  REPORT: "Final Report",
  // W2 steps
  CONTEXTUALIZE: "Context Building",
  GENERATE: "Hypothesis Generation (Parallel)",
  NEGATIVE_FILTER: "Negative Results Filter",
  DEBATE: "QA Debate (Parallel)",
  RANK: "Ranking (Human Checkpoint)",
  EVOLVE: "Hypothesis Refinement",
  RCMXT_PROFILE: "RCMXT Evidence Profile",
  PRESENT: "Present Results",
  // W3 steps
  INGEST: "Data Ingestion",
  QC: "Quality Control",
  PLAN: "Analysis Plan (Human Checkpoint)",
  EXECUTE: "Statistical Execution",
  INTEGRATE: "Multi-omics Integration",
  VALIDATE: "Statistical Validation",
  PLAUSIBILITY: "Biological Plausibility",
  INTERPRET: "Interpretation",
  AUDIT: "Reproducibility Audit",
  // W4 steps
  OUTLINE: "Manuscript Outline (Human Checkpoint)",
  ASSEMBLE: "Reference Assembly",
  DRAFT: "Manuscript Draft",
  FIGURES: "Figure Descriptions",
  STATISTICAL_REVIEW: "Statistical Review",
  PLAUSIBILITY_REVIEW: "Plausibility Review",
  REPRODUCIBILITY_CHECK: "Reproducibility Check",
  REVISION: "Revision",
  // W5 steps
  OPPORTUNITY: "Funding Opportunity",
  SPECIFIC_AIMS: "Specific Aims (Human Checkpoint)",
  STRATEGY: "Research Strategy",
  PRELIMINARY_DATA: "Preliminary Data",
  BUDGET_PLAN: "Budget Plan",
  MOCK_REVIEW: "Mock Review (Parallel)",
  // W6 steps
  EVIDENCE_LANDSCAPE: "Evidence Landscape",
  CLASSIFY: "Contradiction Classification",
  MINE_NEGATIVES: "Negative Results Mining",
  RESOLUTION_HYPOTHESES: "Resolution Hypotheses",
  // W8 steps
  PARSE_SECTIONS: "Parse Sections",
  EXTRACT_CLAIMS: "Claim Extraction",
  CITE_VALIDATION: "Citation Validation",
  BACKGROUND_LIT: "Background Literature",
  // NOVELTY_CHECK already defined for W1 above — shared label
  METHODOLOGY_REVIEW: "Methodology Review",
  EVIDENCE_GRADE: "Evidence Grading (RCMXT)",
  HUMAN_CHECKPOINT: "Human Checkpoint",
  SYNTHESIZE_REVIEW: "Synthesize Review",
  // W9 steps
  PRE_HEALTH_CHECK: "Health Check",
  INGEST_DATA: "Data Ingest",
  GENOMIC_ANALYSIS: "Genomic Analysis (Ensembl/GWAS)",
  EXPRESSION_ANALYSIS: "Expression Analysis (GTEx)",
  PROTEIN_ANALYSIS: "Protein Analysis (UniProt)",
  VARIANT_ANNOTATION: "Variant Annotation (VEP)",
  PATHWAY_ENRICHMENT: "Pathway Enrichment (GO/KEGG)",
  NETWORK_ANALYSIS: "Network Analysis (STRING)",
  DC_PHASE_B: "Direction Check — Phase B",
  CROSS_OMICS_INTEGRATION: "Cross-Omics Integration",
  HC_INTEGRATION: "Human Checkpoint — Integration",
  LITERATURE_COMPARISON: "Literature Comparison",
  NOVELTY_ASSESSMENT: "Novelty Assessment",
  CONTRADICTION_SCAN: "Contradiction Scan",
  INTEGRITY_AUDIT: "Integrity Audit",
  DC_NOVELTY: "Direction Check — Novelty",
  EXPERIMENTAL_DESIGN: "Experimental Design",
  GRANT_RELEVANCE: "Grant Relevance",
  // W10 steps
  COMPOUND_SEARCH: "Compound Search (ChEMBL)",
  BIOACTIVITY_PROFILE: "Bioactivity Profile",
  TARGET_IDENTIFICATION: "Target Identification",
  CLINICAL_TRIALS_SEARCH: "Clinical Trials Search",
  EFFICACY_ANALYSIS: "Efficacy Analysis",
  SAFETY_PROFILE: "Safety & ADMET Profile",
  DC_PRELIMINARY: "Direction Check — Preliminary",
  MECHANISM_REVIEW: "Mechanism of Action Review",
};

const WORKFLOW_STEPS: Record<string, string[]> = {
  W1: [
    "SCOPE", "SEARCH", "SCREEN", "EXTRACT", "NEGATIVE_CHECK", "SYNTHESIZE",
    "CONTRADICTION_CHECK", "CITATION_CHECK", "RCMXT_SCORE", "NOVELTY_CHECK", "REPORT",
  ],
  W2: [
    "CONTEXTUALIZE", "GENERATE", "NEGATIVE_FILTER", "DEBATE", "RANK",
    "EVOLVE", "RCMXT_PROFILE", "PRESENT",
  ],
  W3: [
    "INGEST", "QC", "PLAN", "EXECUTE", "INTEGRATE", "VALIDATE",
    "PLAUSIBILITY", "INTERPRET", "CONTRADICTION_CHECK", "AUDIT", "REPORT",
  ],
  W4: [
    "OUTLINE", "ASSEMBLE", "DRAFT", "FIGURES",
    "STATISTICAL_REVIEW", "PLAUSIBILITY_REVIEW", "REPRODUCIBILITY_CHECK",
    "REVISION", "REPORT",
  ],
  W5: [
    "OPPORTUNITY", "SPECIFIC_AIMS", "STRATEGY", "PRELIMINARY_DATA",
    "BUDGET_PLAN", "MOCK_REVIEW", "REVISION", "REPORT",
  ],
  W6: [
    "EVIDENCE_LANDSCAPE", "CLASSIFY", "MINE_NEGATIVES", "RESOLUTION_HYPOTHESES", "PRESENT",
  ],
  W8: [
    "INGEST", "PARSE_SECTIONS", "EXTRACT_CLAIMS", "CITE_VALIDATION", "BACKGROUND_LIT",
    "NOVELTY_CHECK", "INTEGRITY_AUDIT", "CONTRADICTION_CHECK", "METHODOLOGY_REVIEW",
    "EVIDENCE_GRADE", "HUMAN_CHECKPOINT", "SYNTHESIZE_REVIEW", "REPORT",
  ],
  W9: [
    "PRE_HEALTH_CHECK", "SCOPE", "INGEST_DATA", "QC",
    "GENOMIC_ANALYSIS", "EXPRESSION_ANALYSIS", "PROTEIN_ANALYSIS",
    "VARIANT_ANNOTATION", "PATHWAY_ENRICHMENT", "NETWORK_ANALYSIS", "DC_PHASE_B",
    "CROSS_OMICS_INTEGRATION", "HC_INTEGRATION",
    "LITERATURE_COMPARISON", "NOVELTY_ASSESSMENT", "CONTRADICTION_SCAN",
    "INTEGRITY_AUDIT", "DC_NOVELTY",
    "EXPERIMENTAL_DESIGN", "GRANT_RELEVANCE", "REPORT",
  ],
  W10: [
    "SCOPE", "COMPOUND_SEARCH", "BIOACTIVITY_PROFILE", "TARGET_IDENTIFICATION",
    "CLINICAL_TRIALS_SEARCH", "EFFICACY_ANALYSIS", "SAFETY_PROFILE", "DC_PRELIMINARY",
    "MECHANISM_REVIEW", "LITERATURE_COMPARISON", "GRANT_RELEVANCE", "REPORT",
  ],
};

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

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return "";
  }
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
  // Advanced intervention state
  const [budgetTopup, setBudgetTopup] = useState("1.00");
  const [directionInput, setDirectionInput] = useState("");
  const [stepActioning, setStepActioning] = useState<string | null>(null);

  // Node click → step highlight
  const [activeStep, setActiveStep] = useState<string | null>(null);
  const stepRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const handleStepClick = useCallback((stepId: string) => {
    setActiveStep(stepId);
    stepRefs.current[stepId]?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, []);

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
  }, [selectedId, workflow, workflow?.state, fetchWorkflow]);

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
      await fetchWorkflow();
    } catch {
      // error handled by API client
    } finally {
      setIntervening(false);
    }
  };

  const doResume = async (withBudget = false) => {
    if (!selectedId) return;
    setIntervening(true);
    try {
      const body = withBudget ? { budget_topup: parseFloat(budgetTopup) || 0 } : {};
      await api.post<ResumeResponse>(`/api/v1/workflows/${selectedId}/resume`, body);
      await fetchWorkflow();
    } catch {
      // handled
    } finally {
      setIntervening(false);
    }
  };

  const doDirectionResponse = async () => {
    if (!selectedId || !directionInput.trim()) return;
    setIntervening(true);
    try {
      await api.post(`/api/v1/workflows/${selectedId}/direction_response`, {
        response: directionInput.trim(),
      });
      setDirectionInput("");
      await fetchWorkflow();
    } catch {
      // handled
    } finally {
      setIntervening(false);
    }
  };

  const doStepAction = async (stepId: string, action: "rerun" | "skip") => {
    if (!selectedId) return;
    setStepActioning(stepId);
    try {
      await api.post<StepActionResponse>(
        `/api/v1/workflows/${selectedId}/steps/${stepId}/${action}`,
        {},
      );
      await fetchWorkflow();
    } catch {
      // handled
    } finally {
      setStepActioning(null);
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

              {/* Pipeline Graph */}
              {WORKFLOW_STEPS[workflow.template] && (
                <WorkflowPipelineGraph workflow={workflow} onStepClick={handleStepClick} />
              )}

              {/* Pipeline Steps */}
              <div>
                <p className="mb-2 text-xs font-medium text-muted-foreground">
                  Pipeline Steps ({workflow.step_history.length}/{(WORKFLOW_STEPS[workflow.template] ?? WORKFLOW_STEPS.W1).length})
                </p>
                <div className="space-y-0.5">
                  {(WORKFLOW_STEPS[workflow.template] ?? WORKFLOW_STEPS.W1).map((stepId) => {
                    const historyEntry = workflow.step_history.find(
                      (s) => s.step_id === stepId
                    );
                    const hasData = historyEntry && historyEntry.result_data;
                    const isExpanded = expandedSteps.has(stepId);

                    return (
                      <div
                        key={stepId}
                        ref={(el) => { stepRefs.current[stepId] = el; }}
                        className={activeStep === stepId ? "rounded bg-accent/50 transition-colors" : undefined}
                      >
                        <div className="flex items-center gap-1">
                          <button
                            className="flex flex-1 items-center gap-2 rounded px-2 py-1.5 text-xs hover:bg-accent text-left"
                            onClick={() => hasData && toggleStep(stepId)}
                            disabled={!hasData}
                            aria-expanded={isExpanded}
                            aria-label={`${STEP_LABELS[stepId] ?? stepId}: ${historyEntry ? "completed" : "pending"}`}
                          >
                            {stepStatusIcon(stepId, workflow)}
                            <span className="font-medium flex-1">
                              {STEP_LABELS[stepId] ?? stepId}
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
                          {/* Per-step Rerun / Skip controls */}
                          {historyEntry && ["PAUSED", "FAILED", "OVER_BUDGET"].includes(workflow.state) && (
                            <div className="flex gap-0.5 shrink-0">
                              <button
                                className="rounded p-1 text-muted-foreground hover:text-primary hover:bg-accent"
                                title={`Rerun ${stepId}`}
                                onClick={() => doStepAction(stepId, "rerun")}
                                disabled={stepActioning === stepId}
                                aria-label={`Rerun step ${STEP_LABELS[stepId] ?? stepId}`}
                              >
                                {stepActioning === stepId
                                  ? <Loader2 className="h-3 w-3 animate-spin" />
                                  : <RefreshCw className="h-3 w-3" />}
                              </button>
                              <button
                                className="rounded p-1 text-muted-foreground hover:text-amber-500 hover:bg-accent"
                                title={`Skip ${stepId}`}
                                onClick={() => doStepAction(stepId, "skip")}
                                disabled={!!stepActioning}
                                aria-label={`Skip step ${STEP_LABELS[stepId] ?? stepId}`}
                              >
                                <SkipForward className="h-3 w-3" />
                              </button>
                            </div>
                          )}
                        </div>

                        {/* Expanded step result */}
                        {isExpanded && hasData && (
                          <StepResultPanel data={historyEntry.result_data as Record<string, unknown>} />
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

              {/* WAITING_DIRECTION banner */}
              {workflow.state === "WAITING_DIRECTION" && (
                <>
                  <Separator />
                  <div className="rounded-md border border-violet-500/50 bg-violet-500/10 p-3 space-y-2">
                    <p className="text-xs font-medium text-violet-500">Direction Check</p>
                    <p className="text-xs text-muted-foreground">
                      Provide research direction. Examples:
                      <span className="block font-mono text-[10px] mt-1 space-y-0.5">
                        <span className="block">continue</span>
                        <span className="block">focus:BRCA1,TP53</span>
                        <span className="block">skip_network_analysis</span>
                        <span className="block">adjust:focus on epigenetics only</span>
                      </span>
                    </p>
                    <div className="flex gap-2">
                      <Input
                        value={directionInput}
                        onChange={(e) => setDirectionInput(e.target.value)}
                        placeholder="continue"
                        className="h-7 text-xs font-mono flex-1"
                        onKeyDown={(e) => e.key === "Enter" && doDirectionResponse()}
                      />
                      <Button
                        size="sm"
                        variant="default"
                        disabled={intervening || !directionInput.trim()}
                        onClick={doDirectionResponse}
                        className="h-7 text-xs"
                      >
                        <Navigation className="mr-1 h-3 w-3" /> Send
                      </Button>
                    </div>
                  </div>
                </>
              )}

              {/* OVER_BUDGET banner */}
              {workflow.state === "OVER_BUDGET" && (
                <>
                  <Separator />
                  <div className="rounded-md border border-amber-500/50 bg-amber-500/10 p-3 space-y-2">
                    <p className="text-xs font-medium text-amber-500">Budget Exhausted</p>
                    <p className="text-xs text-muted-foreground">
                      Add budget to resume the workflow from where it stopped.
                    </p>
                    <div className="flex items-center gap-2">
                      <DollarSign className="h-3.5 w-3.5 text-amber-500 shrink-0" />
                      <Input
                        type="number"
                        min="0.5"
                        max="50"
                        step="0.5"
                        value={budgetTopup}
                        onChange={(e) => setBudgetTopup(e.target.value)}
                        className="h-7 w-24 text-xs font-mono"
                      />
                      <span className="text-xs text-muted-foreground">USD top-up</span>
                      <Button
                        size="sm"
                        variant="default"
                        disabled={intervening}
                        onClick={() => doResume(true)}
                        className="h-7 text-xs ml-auto"
                      >
                        <Play className="mr-1 h-3 w-3" /> Resume
                      </Button>
                    </div>
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
                <div className="flex gap-2 flex-wrap" role="group" aria-label="Workflow intervention actions">
                  {workflow.state === "WAITING_HUMAN" && (
                    <Button
                      size="sm"
                      variant="default"
                      disabled={intervening}
                      onClick={() => doResume()}
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
                  {(workflow.state === "PAUSED" || workflow.state === "FAILED") && (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={intervening}
                      onClick={() => doResume()}
                      aria-label={`Resume workflow ${workflow.template}`}
                    >
                      <Play className="mr-1 h-3 w-3" aria-hidden="true" /> Resume
                    </Button>
                  )}
                  {["PENDING", "RUNNING", "PAUSED", "WAITING_HUMAN", "WAITING_DIRECTION", "OVER_BUDGET"].includes(workflow.state) && (
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
                {["RUNNING", "PAUSED", "WAITING_HUMAN", "WAITING_DIRECTION"].includes(workflow.state) && (
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
