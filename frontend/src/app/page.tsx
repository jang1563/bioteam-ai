"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AgentGrid } from "@/components/dashboard/agent-grid";
import { WorkflowCard } from "@/components/dashboard/workflow-card";
import { ActivityFeed } from "@/components/dashboard/activity-feed";
import { AgentDetailSheet } from "@/components/dashboard/agent-detail-sheet";
import { WorkflowDetailSheet } from "@/components/dashboard/workflow-detail-sheet";
import { CreateWorkflowDialog } from "@/components/dashboard/create-workflow-dialog";
import {
  AgentGridSkeleton,
  WorkflowListSkeleton,
  ActivityFeedSkeleton,
} from "@/components/dashboard/loading-skeletons";
import { useAgents } from "@/hooks/use-agents";
import { useWorkflows } from "@/hooks/use-workflows";
import { useSSE } from "@/hooks/use-sse";
import { useAppStore } from "@/stores/app-store";
import { api } from "@/lib/api-client";
import type { ColdStartStatus, ColdStartResponse } from "@/types/api";
import { AlertTriangle, Loader2, Rocket, Database } from "lucide-react";

function ColdStartBanner() {
  const [status, setStatus] = useState<ColdStartStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [quickStarting, setQuickStarting] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const data = await api.get<ColdStartStatus>("/api/v1/cold-start/status");
      setStatus(data);
    } catch {
      // Backend might not be running — just hide the banner
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  const handleQuickStart = async () => {
    setQuickStarting(true);
    try {
      await api.post<ColdStartResponse>("/api/v1/cold-start/quick");
      await fetchStatus();
    } catch {
      // Silently fail — user can retry from Settings
    } finally {
      setQuickStarting(false);
    }
  };

  if (loading || dismissed || !status) return null;

  // Fully initialized — no banner needed
  if (status.is_initialized && status.critical_agents_healthy && status.has_literature) {
    return null;
  }

  const issues: string[] = [];
  if (!status.is_initialized) issues.push("System not initialized");
  if (!status.critical_agents_healthy) issues.push("Some critical agents unhealthy");
  if (!status.has_literature) issues.push("No literature seeded");
  if (!status.has_lab_kb) issues.push("No Lab KB entries");

  const severity = !status.is_initialized || !status.critical_agents_healthy ? "error" : "warning";

  return (
    <Card className={severity === "error" ? "border-destructive" : "border-yellow-500/50"}>
      <CardContent className="py-3">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <AlertTriangle
              className={`mt-0.5 h-4 w-4 shrink-0 ${severity === "error" ? "text-destructive" : "text-yellow-500"}`}
            />
            <div className="space-y-1">
              <p className="text-sm font-medium">
                {!status.is_initialized ? "Cold Start Required" : "Setup Incomplete"}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {issues.map((issue) => (
                  <Badge key={issue} variant="outline" className="text-xs">
                    {issue}
                  </Badge>
                ))}
              </div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Database className="h-3 w-3" />
                {status.total_documents} documents | {status.agents_registered} agents
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Button
              size="sm"
              variant="outline"
              onClick={handleQuickStart}
              disabled={quickStarting}
            >
              {quickStarting ? (
                <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />
              ) : (
                <Rocket className="mr-1.5 h-3 w-3" />
              )}
              Quick Start
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="text-xs"
              onClick={() => setDismissed(true)}
            >
              Dismiss
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function MissionControlPage() {
  const { agents, loading: agentsLoading } = useAgents();
  const { workflows, loading: workflowsLoading, refresh: refreshWorkflows } = useWorkflows();
  const events = useAppStore((s) => s.events);
  const addEvent = useAppStore((s) => s.addEvent);

  useSSE((event) => {
    addEvent(event);
    if (event.event_type.startsWith("workflow.")) {
      refreshWorkflows();
    }
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">Mission Control</h1>
        <CreateWorkflowDialog onCreated={refreshWorkflows} />
      </div>

      {/* Cold Start Banner */}
      <ColdStartBanner />

      {/* Agent Grid */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">
            Agents {!agentsLoading && `(${agents.length})`}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {agentsLoading ? <AgentGridSkeleton /> : <AgentGrid agents={agents} />}
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Workflows */}
        <div className="space-y-3 lg:col-span-2">
          <h2 className="text-sm font-medium text-muted-foreground">
            Active Workflows {!workflowsLoading && `(${workflows.length})`}
          </h2>
          {workflowsLoading ? (
            <WorkflowListSkeleton />
          ) : workflows.length === 0 ? (
            <Card className="border-dashed">
              <CardContent className="py-8 text-center text-sm text-muted-foreground">
                No workflows yet. Create one to get started.
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {workflows.map((wf) => (
                <WorkflowCard key={wf.id} workflow={wf} />
              ))}
            </div>
          )}
        </div>

        {/* Activity Feed */}
        <div>
          <h2 className="mb-3 text-sm font-medium text-muted-foreground">
            Activity Feed
          </h2>
          <Card>
            <CardContent className="p-3">
              {events.length === 0 && agentsLoading ? (
                <ActivityFeedSkeleton />
              ) : (
                <ActivityFeed events={events} />
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Detail Sheets */}
      <AgentDetailSheet />
      <WorkflowDetailSheet />
    </div>
  );
}
