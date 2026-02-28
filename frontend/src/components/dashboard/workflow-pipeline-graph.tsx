"use client";

import { useMemo, useCallback } from "react";
import {
  ReactFlow,
  Background,
  type Node,
  type Edge,
  type NodeTypes,
  type NodeProps,
  Handle,
  Position,
  BackgroundVariant,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { WorkflowStatus } from "@/types/api";

interface StepDef {
  id: string;
  label: string;
  short: string;
  human?: boolean;
}

const W1_STEPS: StepDef[] = [
  { id: "SCOPE", label: "Scope Definition", short: "Scope" },
  { id: "SEARCH", label: "Literature Search", short: "Search" },
  { id: "SCREEN", label: "Paper Screening", short: "Screen" },
  { id: "EXTRACT", label: "Data Extraction", short: "Extract" },
  { id: "NEGATIVE_CHECK", label: "Negative Results", short: "NR Check" },
  { id: "SYNTHESIZE", label: "Synthesis", short: "Synthesis", human: true },
  { id: "CONTRADICTION_CHECK", label: "Contradiction Detection", short: "Contradict" },
  { id: "CITATION_CHECK", label: "Citation Check", short: "Citations" },
  { id: "RCMXT_SCORE", label: "Evidence Scoring", short: "RCMXT" },
  { id: "NOVELTY_CHECK", label: "Novelty Check", short: "Novelty" },
  { id: "REPORT", label: "Final Report", short: "Report" },
];

const W2_STEPS: StepDef[] = [
  { id: "CONTEXTUALIZE", label: "Context Building", short: "Context" },
  { id: "GENERATE", label: "Hypothesis Generation", short: "Generate" },
  { id: "NEGATIVE_FILTER", label: "Negative Filter", short: "NR Filter" },
  { id: "DEBATE", label: "QA Debate", short: "Debate" },
  { id: "RANK", label: "Ranking", short: "Rank", human: true },
  { id: "EVOLVE", label: "Refinement", short: "Evolve" },
  { id: "RCMXT_PROFILE", label: "Evidence Profile", short: "RCMXT" },
  { id: "PRESENT", label: "Present Results", short: "Present" },
];

const W3_STEPS: StepDef[] = [
  { id: "INGEST", label: "Data Ingestion", short: "Ingest" },
  { id: "QC", label: "Quality Control", short: "QC" },
  { id: "PLAN", label: "Analysis Plan", short: "Plan", human: true },
  { id: "EXECUTE", label: "Execution", short: "Execute" },
  { id: "INTEGRATE", label: "Integration", short: "Integrate" },
  { id: "VALIDATE", label: "Validation", short: "Validate" },
  { id: "PLAUSIBILITY", label: "Plausibility", short: "Plausible" },
  { id: "INTERPRET", label: "Interpretation", short: "Interpret" },
  { id: "CONTRADICTION_CHECK", label: "Contradiction", short: "Contradict" },
  { id: "AUDIT", label: "Audit", short: "Audit" },
  { id: "REPORT", label: "Final Report", short: "Report" },
];

const W4_STEPS: StepDef[] = [
  { id: "OUTLINE", label: "Outline", short: "Outline", human: true },
  { id: "ASSEMBLE", label: "Reference Assembly", short: "Assemble" },
  { id: "DRAFT", label: "Manuscript Draft", short: "Draft" },
  { id: "FIGURES", label: "Figures", short: "Figures" },
  { id: "STATISTICAL_REVIEW", label: "Stats Review", short: "Stats" },
  { id: "PLAUSIBILITY_REVIEW", label: "Plausibility", short: "Plausible" },
  { id: "REPRODUCIBILITY_CHECK", label: "Reproducibility", short: "Reprod." },
  { id: "REVISION", label: "Revision", short: "Revision" },
  { id: "REPORT", label: "Final Report", short: "Report" },
];

const W5_STEPS: StepDef[] = [
  { id: "OPPORTUNITY", label: "Opportunity", short: "Opp." },
  { id: "SPECIFIC_AIMS", label: "Specific Aims", short: "Aims", human: true },
  { id: "STRATEGY", label: "Strategy", short: "Strategy" },
  { id: "PRELIMINARY_DATA", label: "Preliminary Data", short: "Prelim" },
  { id: "BUDGET_PLAN", label: "Budget Plan", short: "Budget" },
  { id: "MOCK_REVIEW", label: "Mock Review", short: "Review" },
  { id: "REVISION", label: "Revision", short: "Revision" },
  { id: "REPORT", label: "Final Report", short: "Report" },
];

const W6_STEPS: StepDef[] = [
  { id: "EVIDENCE_LANDSCAPE", label: "Evidence Landscape", short: "Landscape" },
  { id: "CLASSIFY", label: "Contradiction Classification", short: "Classify" },
  { id: "MINE_NEGATIVES", label: "Negative Results Mining", short: "Mine NR" },
  { id: "RESOLUTION_HYPOTHESES", label: "Resolution Hypotheses", short: "Hypotheses" },
  { id: "PRESENT", label: "Present Results", short: "Present" },
];

const W8_STEPS: StepDef[] = [
  { id: "INGEST", label: "PDF Ingest", short: "Ingest" },
  { id: "PARSE", label: "Section Parse", short: "Parse" },
  { id: "EXTRACT_CLAIMS", label: "Claim Extraction", short: "Claims" },
  { id: "CITE_VALIDATION", label: "Citation Check", short: "Citations" },
  { id: "BACKGROUND_LIT", label: "Background Lit", short: "Background" },
  { id: "INTEGRITY_AUDIT", label: "Integrity Audit", short: "Integrity" },
  { id: "CONTRADICTION_CHECK", label: "Contradiction Check", short: "Contradictions" },
  { id: "METHODOLOGY_REVIEW", label: "Methodology Review", short: "Methods" },
  { id: "EVIDENCE_GRADE", label: "Evidence Grading", short: "RCMXT" },
  { id: "HUMAN_CHECKPOINT", label: "Human Review", short: "HC", human: true },
  { id: "SYNTHESIZE_REVIEW", label: "Synthesize Review", short: "Synthesize" },
  { id: "REPORT", label: "Final Report", short: "Report" },
];

// W9: 21-step multi-omics pipeline — 5 phases, 3 HC + 3 DC
// Displayed in 3 rows (Phase A top, Phase B middle, Phases C-E bottom)
const W9_STEPS: StepDef[] = [
  // Phase A
  { id: "PRE_HEALTH_CHECK", label: "Health Check", short: "Health" },
  { id: "SCOPE", label: "Research Scope", short: "Scope", human: true },
  { id: "INGEST_DATA", label: "Data Ingest", short: "Ingest" },
  { id: "QC", label: "Quality Control", short: "QC", human: true },
  // Phase B
  { id: "GENOMIC_ANALYSIS", label: "Genomic Analysis", short: "Genomics" },
  { id: "EXPRESSION_ANALYSIS", label: "Expression Analysis", short: "Expression" },
  { id: "PROTEIN_ANALYSIS", label: "Protein Analysis", short: "Proteomics" },
  { id: "VARIANT_ANNOTATION", label: "Variant Annotation (VEP)", short: "VEP" },
  { id: "PATHWAY_ENRICHMENT", label: "Pathway Enrichment", short: "GO/KEGG" },
  { id: "NETWORK_ANALYSIS", label: "Network Analysis", short: "Network" },
  { id: "DC_PHASE_B", label: "Direction Check B", short: "DC-B" },
  // Phase C
  { id: "CROSS_OMICS_INTEGRATION", label: "Cross-Omics Integration", short: "Integration" },
  { id: "HC_INTEGRATION", label: "Human Checkpoint", short: "HC-C", human: true },
  // Phase D
  { id: "LITERATURE_COMPARISON", label: "Literature Comparison", short: "Lit. Compare" },
  { id: "NOVELTY_ASSESSMENT", label: "Novelty Assessment", short: "Novelty" },
  { id: "CONTRADICTION_SCAN", label: "Contradiction Scan", short: "Contradict" },
  { id: "INTEGRITY_AUDIT", label: "Integrity Audit", short: "Integrity" },
  { id: "DC_NOVELTY", label: "Direction Check D", short: "DC-D" },
  // Phase E
  { id: "EXPERIMENTAL_DESIGN", label: "Experimental Design", short: "Exp. Design" },
  { id: "GRANT_RELEVANCE", label: "Grant Relevance", short: "Grant" },
  { id: "REPORT", label: "Final Report", short: "Report" },
];

const WORKFLOW_STEP_DEFS: Record<string, StepDef[]> = {
  W1: W1_STEPS,
  W2: W2_STEPS,
  W3: W3_STEPS,
  W4: W4_STEPS,
  W5: W5_STEPS,
  W6: W6_STEPS,
  W8: W8_STEPS,
  W9: W9_STEPS,
};

type StepStatus = "completed" | "running" | "waiting" | "failed" | "pending";

interface StepNodeData {
  label: string;
  short: string;
  status: StepStatus;
  isHuman: boolean;
  [key: string]: unknown;
}

const STATUS_STYLES: Record<StepStatus, { bg: string; border: string; text: string; icon: string }> = {
  completed: {
    bg: "rgba(16, 185, 129, 0.1)",
    border: "rgb(16, 185, 129)",
    text: "rgb(16, 185, 129)",
    icon: "✓",
  },
  running: {
    bg: "rgba(59, 130, 246, 0.1)",
    border: "rgb(59, 130, 246)",
    text: "rgb(59, 130, 246)",
    icon: "⟳",
  },
  waiting: {
    bg: "rgba(245, 158, 11, 0.1)",
    border: "rgb(245, 158, 11)",
    text: "rgb(245, 158, 11)",
    icon: "⏸",
  },
  failed: {
    bg: "rgba(239, 68, 68, 0.1)",
    border: "rgb(239, 68, 68)",
    text: "rgb(239, 68, 68)",
    icon: "✗",
  },
  pending: {
    bg: "rgba(148, 163, 184, 0.05)",
    border: "rgba(148, 163, 184, 0.3)",
    text: "rgb(148, 163, 184)",
    icon: "○",
  },
};

function StepNode({ data }: NodeProps<Node<StepNodeData>>) {
  const style = STATUS_STYLES[data.status];
  const isActive = data.status === "running" || data.status === "waiting";

  return (
    <>
      <Handle type="target" position={Position.Left} className="!w-1.5 !h-1.5 !border-0 !bg-border" />
      <div
        className="px-3 py-2 rounded-lg text-center min-w-[90px] transition-all duration-300"
        style={{
          background: style.bg,
          border: `1.5px solid ${style.border}`,
          boxShadow: isActive ? `0 0 12px ${style.border}40` : "none",
        }}
      >
        <div className="flex items-center justify-center gap-1.5">
          <span
            className="text-[10px] font-bold"
            style={{ color: style.text, animation: data.status === "running" ? "spin 1.5s linear infinite" : "none" }}
          >
            {style.icon}
          </span>
          <span
            className="text-[11px] font-medium leading-tight"
            style={{ color: style.text }}
          >
            {data.short}
          </span>
        </div>
        {data.isHuman && (
          <div
            className="mt-0.5 text-[8px] font-medium tracking-wide uppercase"
            style={{ color: style.text, opacity: 0.7 }}
          >
            Human Review
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Right} className="!w-1.5 !h-1.5 !border-0 !bg-border" />
    </>
  );
}

const nodeTypes: NodeTypes = { step: StepNode };

function getStepStatus(stepId: string, workflow: WorkflowStatus): StepStatus {
  const completed = workflow.step_history.some((s) => s.step_id === stepId);
  const isCurrent = workflow.current_step === stepId;

  if (completed && !isCurrent) return "completed";
  if (isCurrent && workflow.state === "RUNNING") return "running";
  if (isCurrent && workflow.state === "WAITING_HUMAN") return "waiting";
  if (isCurrent && workflow.state === "FAILED") return "failed";
  if (isCurrent && workflow.state === "PAUSED") return "waiting";
  return "pending";
}

function layoutNodes(steps: StepDef[], workflow: WorkflowStatus) {
  const nodeWidth = 110;
  const nodeHeight = 50;
  const gapX = 16;
  const gapY = 60;
  const startX = 20;
  const startY = 20;

  // Use 3 rows for very long pipelines (>14 steps), 2 rows for medium (>6), 1 row for short
  const useThreeRows = steps.length > 14;
  const useTwoRows = !useThreeRows && steps.length > 6;
  const rowCount = useThreeRows ? 3 : useTwoRows ? 2 : 1;
  const perRow = Math.ceil(steps.length / rowCount);

  const ns: Node<StepNodeData>[] = steps.map((step, i) => {
    let x: number;
    let y: number;

    if (useThreeRows) {
      const row = Math.floor(i / perRow);
      const col = row % 2 === 0 ? i - row * perRow : perRow - 1 - (i - row * perRow); // snake
      x = startX + col * (nodeWidth + gapX);
      y = startY + row * (nodeHeight + gapY);
    } else if (useTwoRows) {
      const topCount = Math.ceil(steps.length / 2);
      const row = i < topCount ? 0 : 1;
      const col = row === 0 ? i : steps.length - 1 - i; // reverse for bottom row (snake)
      x = startX + col * (nodeWidth + gapX);
      y = startY + row * (nodeHeight + gapY);
    } else {
      x = startX + i * (nodeWidth + gapX);
      y = startY;
    }

    return {
      id: step.id,
      type: "step",
      position: { x, y },
      data: {
        label: step.label,
        short: step.short,
        status: getStepStatus(step.id, workflow),
        isHuman: !!step.human,
      },
      draggable: false,
    };
  });

  const es: Edge[] = [];
  for (let i = 0; i < steps.length - 1; i++) {
    const sourceStatus = getStepStatus(steps[i].id, workflow);
    const targetStatus = getStepStatus(steps[i + 1].id, workflow);
    const isActive = sourceStatus === "completed" && (targetStatus === "running" || targetStatus === "waiting");
    const isPast = sourceStatus === "completed" && targetStatus === "completed";

    es.push({
      id: `e-${steps[i].id}-${steps[i + 1].id}`,
      source: steps[i].id,
      target: steps[i + 1].id,
      type: "smoothstep",
      animated: isActive,
      style: {
        stroke: isPast
          ? "rgb(16, 185, 129)"
          : isActive
            ? "rgb(59, 130, 246)"
            : "rgba(148, 163, 184, 0.3)",
        strokeWidth: isPast || isActive ? 2 : 1,
      },
    });
  }

  return { nodes: ns, edges: es, rowCount };
}

export function WorkflowPipelineGraph({ workflow }: { workflow: WorkflowStatus }) {
  const steps = WORKFLOW_STEP_DEFS[workflow.template] ?? W1_STEPS;

  const { nodes, edges, rowCount } = useMemo(
    () => layoutNodes(steps, workflow),
    [steps, workflow],
  );

  const onInit = useCallback((instance: { fitView: () => void }) => {
    instance.fitView();
  }, []);

  const height = rowCount === 3 ? 280 : rowCount === 2 ? 200 : 120;

  return (
    <div className={`w-full rounded-lg border border-border overflow-hidden bg-background/50`} style={{ height }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onInit={onInit}
        fitView
        proOptions={{ hideAttribution: true }}
        panOnDrag={false}
        zoomOnScroll={false}
        zoomOnPinch={false}
        zoomOnDoubleClick={false}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        minZoom={0.5}
        maxZoom={1}
      >
        <Background variant={BackgroundVariant.Dots} gap={16} size={0.5} className="!bg-transparent" />
      </ReactFlow>
    </div>
  );
}
