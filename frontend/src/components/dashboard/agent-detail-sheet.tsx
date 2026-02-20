"use client";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { useAgentDetail } from "@/hooks/use-agents";
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
              ? `View details for ${agent.name} agent (${agent.state})`
              : "Loading agent details"}
          </SheetDescription>
        </SheetHeader>

        {loading && (
          <p className="py-4 text-sm text-muted-foreground">Loading...</p>
        )}

        {agent && (
          <div className="mt-4 space-y-4">
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
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span className={mono ? "font-mono text-xs" : ""}>{value}</span>
    </div>
  );
}
