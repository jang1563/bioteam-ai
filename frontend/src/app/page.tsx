"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AgentGrid } from "@/components/dashboard/agent-grid";
import { WorkflowCard } from "@/components/dashboard/workflow-card";
import { ActivityFeed } from "@/components/dashboard/activity-feed";
import { AgentDetailSheet } from "@/components/dashboard/agent-detail-sheet";
import { WorkflowDetailSheet } from "@/components/dashboard/workflow-detail-sheet";
import { CreateWorkflowDialog } from "@/components/dashboard/create-workflow-dialog";
import { useAgents } from "@/hooks/use-agents";
import { useWorkflows } from "@/hooks/use-workflows";
import { useSSE } from "@/hooks/use-sse";
import { useAppStore } from "@/stores/app-store";

export default function MissionControlPage() {
  const { agents } = useAgents();
  const { workflows, refresh: refreshWorkflows } = useWorkflows();
  const events = useAppStore((s) => s.events);
  const addEvent = useAppStore((s) => s.addEvent);

  useSSE((event) => {
    addEvent(event);
    // Auto-refresh workflows on workflow events
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
            Agents ({agents.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          <AgentGrid agents={agents} />
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Workflows */}
        <div className="space-y-3 lg:col-span-2">
          <h2 className="text-sm font-medium text-muted-foreground">
            Active Workflows ({workflows.length})
          </h2>
          {workflows.length === 0 ? (
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
              <ActivityFeed events={events} />
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
