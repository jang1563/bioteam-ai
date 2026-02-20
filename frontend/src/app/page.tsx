"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
