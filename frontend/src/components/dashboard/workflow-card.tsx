"use client";

import { Clock, Play, Pause, XCircle, CheckCircle2, AlertTriangle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import type { WorkflowStatus } from "@/types/api";
import { useAppStore } from "@/stores/app-store";

const stateConfig: Record<string, { icon: React.ElementType; color: string; label: string }> = {
  PENDING: { icon: Clock, color: "text-muted-foreground", label: "Pending" },
  RUNNING: { icon: Play, color: "text-emerald-500", label: "Running" },
  PAUSED: { icon: Pause, color: "text-amber-500", label: "Paused" },
  WAITING_HUMAN: { icon: Pause, color: "text-blue-500", label: "Awaiting Input" },
  COMPLETED: { icon: CheckCircle2, color: "text-emerald-500", label: "Completed" },
  FAILED: { icon: AlertTriangle, color: "text-destructive", label: "Failed" },
  CANCELLED: { icon: XCircle, color: "text-muted-foreground", label: "Cancelled" },
  OVER_BUDGET: { icon: AlertTriangle, color: "text-amber-500", label: "Over Budget" },
};

interface WorkflowCardProps {
  workflow: WorkflowStatus;
}

export function WorkflowCard({ workflow }: WorkflowCardProps) {
  const setSelected = useAppStore((s) => s.setSelectedWorkflowId);
  const config = stateConfig[workflow.state] ?? stateConfig.PENDING;
  const Icon = config.icon;
  const budgetUsed = workflow.budget_total - workflow.budget_remaining;
  const budgetPct = workflow.budget_total > 0
    ? Math.round((budgetUsed / workflow.budget_total) * 100)
    : 0;
  const stepsCompleted = workflow.step_history.length;

  return (
    <Card
      className="cursor-pointer transition-all hover:border-primary/40 hover:shadow-md"
      onClick={() => setSelected(workflow.id)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          setSelected(workflow.id);
        }
      }}
      role="button"
      tabIndex={0}
      aria-label={`Workflow ${workflow.template}, status: ${config.label}, budget: $${budgetUsed.toFixed(2)} of $${workflow.budget_total.toFixed(2)}, ${stepsCompleted} steps completed`}
    >
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium">
          {workflow.template}
        </CardTitle>
        <Badge variant="outline" className={cn("flex items-center gap-1", config.color)}>
          <Icon className="h-3 w-3" aria-hidden="true" />
          {config.label}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>Step: {workflow.current_step || "—"}</span>
          <span>{stepsCompleted} completed</span>
        </div>

        {/* Budget bar */}
        <div className="space-y-1">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">Budget</span>
            <span className="font-mono text-muted-foreground">
              ${budgetUsed.toFixed(2)} / ${workflow.budget_total.toFixed(2)}
            </span>
          </div>
          <Progress
            value={budgetPct}
            className="h-1.5"
            aria-label={`Budget usage: ${budgetPct}%`}
          />
        </div>

        {/* ID preview */}
        <p className="font-mono text-[10px] text-muted-foreground/60 truncate">
          {workflow.id}
        </p>
      </CardContent>
    </Card>
  );
}
