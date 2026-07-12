"use client";

import { useState } from "react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useAgentDetail, useAgentQuery, useAgentHistory } from "@/hooks/use-agents";
import { useAppStore } from "@/stores/app-store";

export function AgentDetailSheet() {
  const selectedId = useAppStore((s) => s.selectedAgentId);
  const setSelected = useAppStore((s) => s.setSelectedAgentId);
  const { agent, loading } = useAgentDetail(selectedId);

  return (
    <Sheet open={!!selectedId} onOpenChange={(open) => !open && setSelected(null)}>
      <SheetContent className="w-[450px] overflow-y-auto sm:max-w-[450px]">
        <SheetHeader>
          <SheetTitle>{agent?.name ?? "Agent Detail"}</SheetTitle>
          <SheetDescription>
            {agent
              ? `${agent.name} — ${agent.tier} tier (${agent.state})`
              : "Loading agent details"}
          </SheetDescription>
        </SheetHeader>

        {loading && (
          <p className="py-4 text-sm text-muted-foreground">Loading...</p>
        )}

        {agent && (
          <Tabs defaultValue="overview" className="mt-4">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="ask">Ask Agent</TabsTrigger>
              <TabsTrigger value="history">History</TabsTrigger>
            </TabsList>

            <TabsContent value="overview" className="space-y-4 pt-2">
              <OverviewTab agent={agent} />
            </TabsContent>

            <TabsContent value="ask" className="space-y-4 pt-2">
              <AskAgentTab agentId={agent.id} />
            </TabsContent>

            <TabsContent value="history" className="space-y-4 pt-2">
              <HistoryTab agentId={agent.id} />
            </TabsContent>
          </Tabs>
        )}
      </SheetContent>
    </Sheet>
  );
}

// === Overview Tab (original content) ===

function OverviewTab({ agent }: { agent: NonNullable<ReturnType<typeof useAgentDetail>["agent"]> }) {
  return (
    <>
      {/* Status */}
      <div className="flex items-center gap-2">
        <Badge variant={agent.state === "busy" ? "default" : "secondary"}>
          {agent.state}
        </Badge>
        <Badge variant="outline">{agent.model_tier}</Badge>
        {agent.model_tier_secondary && (
          <Badge variant="outline">{agent.model_tier_secondary}</Badge>
        )}
      </div>

      <Separator />

      {/* Info */}
      <div className="space-y-2 text-sm">
        <Row label="ID" value={agent.id} mono />
        <Row label="Tier" value={agent.tier} />
        <Row label="Division" value={agent.division ?? "—"} />
        <Row label="Criticality" value={agent.criticality} />
        <Row label="Version" value={agent.version || "—"} />
      </div>

      <Separator />

      {/* Tools */}
      {agent.tools.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-medium text-muted-foreground">Tools</p>
          <div className="flex flex-wrap gap-1">
            {agent.tools.map((t) => (
              <Badge key={t} variant="outline" className="text-xs">
                {t}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {agent.mcp_access.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-medium text-muted-foreground">MCP Access</p>
          <div className="flex flex-wrap gap-1">
            {agent.mcp_access.map((m) => (
              <Badge key={m} variant="outline" className="text-xs">
                {m}
              </Badge>
            ))}
          </div>
        </div>
      )}

      <Separator />

      {/* Stats */}
      <div className="space-y-2 text-sm">
        <Row label="Total Calls" value={String(agent.total_calls)} />
        <Row label="Total Cost" value={`$${agent.total_cost.toFixed(4)}`} mono />
        <Row label="Failures" value={String(agent.consecutive_failures)} />
        <Row
          label="Literature Access"
          value={agent.literature_access ? "Yes" : "No"}
        />
      </div>
    </>
  );
}

// === Ask Agent Tab ===

function AskAgentTab({ agentId }: { agentId: string }) {
  const [query, setQuery] = useState("");
  const { answer, loading, error, execute } = useAgentQuery(agentId);

  const handleSubmit = () => {
    if (!query.trim()) return;
    execute(query.trim());
  };

  return (
    <>
      <div className="space-y-2">
        <Textarea
          placeholder="Ask this agent a question..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          rows={3}
          className="resize-none"
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              handleSubmit();
            }
          }}
        />
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">
            {query.length}/5000
          </span>
          <Button
            size="sm"
            onClick={handleSubmit}
            disabled={loading || !query.trim()}
          >
            {loading ? "Asking..." : "Ask"}
          </Button>
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {answer && (
        <div className="space-y-2">
          <Separator />
          <div className="rounded-md border bg-muted/50 p-3">
            <p className="whitespace-pre-wrap text-sm">{answer.answer}</p>
          </div>
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>Cost: ${answer.cost.toFixed(4)}</span>
            <span>{answer.duration_ms}ms</span>
          </div>
        </div>
      )}
    </>
  );
}

// === History Tab ===

function HistoryTab({ agentId }: { agentId: string }) {
  const { history, loading, error, loadMore } = useAgentHistory(agentId);

  if (loading && !history) {
    return <p className="text-sm text-muted-foreground">Loading history...</p>;
  }

  if (error) {
    return (
      <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
        {error}
      </div>
    );
  }

  if (!history || history.entries.length === 0) {
    return (
      <div className="py-8 text-center text-sm text-muted-foreground">
        No execution history yet
      </div>
    );
  }

  return (
    <>
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>{history.total_count} executions</span>
        <span>Total: ${history.total_cost.toFixed(4)}</span>
      </div>

      <div className="space-y-2">
        {history.entries.map((entry, i) => (
          <div key={i} className="rounded-md border p-2 text-sm">
            <div className="flex items-center justify-between">
              <Badge variant={entry.success ? "secondary" : "destructive"} className="text-xs">
                {entry.success ? "OK" : "FAIL"}
              </Badge>
              <span className="text-xs text-muted-foreground">
                {new Date(entry.timestamp).toLocaleString()}
              </span>
            </div>
            {entry.workflow_id && (
              <p className="mt-1 font-mono text-xs text-muted-foreground">
                {entry.workflow_id.slice(0, 8)}... / {entry.step_id}
              </p>
            )}
            {entry.summary && (
              <p className="mt-1 text-xs">{entry.summary}</p>
            )}
            {entry.cost > 0 && (
              <p className="mt-1 text-xs text-muted-foreground">
                ${entry.cost.toFixed(4)}
              </p>
            )}
          </div>
        ))}
      </div>

      {history.total_count > history.entries.length && (
        <Button
          variant="outline"
          size="sm"
          className="w-full"
          onClick={() => loadMore(20, history.entries.length)}
          disabled={loading}
        >
          {loading ? "Loading..." : "Load More"}
        </Button>
      )}
    </>
  );
}

// === Shared ===

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span className={mono ? "font-mono text-xs" : ""}>{value}</span>
    </div>
  );
}
