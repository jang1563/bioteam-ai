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

const W6_STEPS: StepDef[] = [
  { id: "EVIDENCE_LANDSCAPE", label: "Evidence Landscape", short: "Landscape" },
  { id: "CLASSIFY", label: "Contradiction Classification", short: "Classify" },
  { id: "MINE_NEGATIVES", label: "Negative Results Mining", short: "Mine NR" },
  { id: "RESOLUTION_HYPOTHESES", label: "Resolution Hypotheses", short: "Hypotheses" },
  { id: "PRESENT", label: "Present Results", short: "Present" },
];

const WORKFLOW_STEP_DEFS: Record<string, StepDef[]> = {
  W1: W1_STEPS,
  W6: W6_STEPS,
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

  const useTwoRows = steps.length > 6;
  const topCount = useTwoRows ? Math.ceil(steps.length / 2) : steps.length;

  const ns: Node<StepNodeData>[] = steps.map((step, i) => {
    let x: number;
    let y: number;

    if (useTwoRows) {
      const row = i < topCount ? 0 : 1;
      const col = row === 0 ? i : steps.length - 1 - i; // reverse for bottom row
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

  return { nodes: ns, edges: es, useTwoRows };
}

export function WorkflowPipelineGraph({ workflow }: { workflow: WorkflowStatus }) {
  const steps = WORKFLOW_STEP_DEFS[workflow.template] ?? W1_STEPS;

  const { nodes, edges, useTwoRows } = useMemo(
    () => layoutNodes(steps, workflow),
    [steps, workflow],
  );

  const onInit = useCallback((instance: { fitView: () => void }) => {
    instance.fitView();
  }, []);

  const height = useTwoRows ? 200 : 120;

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
