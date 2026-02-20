"use client";

import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { SSEEvent } from "@/types/api";

const eventColors: Record<string, string> = {
  "workflow.created": "text-blue-400",
  "workflow.step_started": "text-muted-foreground",
  "workflow.step_completed": "text-emerald-400",
  "workflow.completed": "text-emerald-500",
  "workflow.failed": "text-destructive",
  "workflow.paused": "text-amber-400",
  "workflow.resumed": "text-blue-400",
  "workflow.cancelled": "text-muted-foreground",
  "agent.status_changed": "text-purple-400",
  "system.alert": "text-amber-500",
};

interface ActivityFeedProps {
  events: SSEEvent[];
}

export function ActivityFeed({ events }: ActivityFeedProps) {
  if (events.length === 0) {
    return (
      <div className="flex items-center justify-center py-8 text-xs text-muted-foreground">
        Waiting for events...
      </div>
    );
  }

  return (
    <ScrollArea className="h-[300px]">
      <div
        role="log"
        aria-label="Activity feed"
        aria-live="polite"
        className="space-y-1 pr-3"
      >
        {events.map((event, i) => (
          <div
            key={`${event.timestamp}-${i}`}
            className="flex items-start gap-2 rounded px-2 py-1.5 text-xs hover:bg-accent"
          >
            <span
              aria-hidden="true"
              className={cn(
                "mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full",
                eventColors[event.event_type]
                  ? eventColors[event.event_type].replace("text-", "bg-")
                  : "bg-muted-foreground",
              )}
            />
            <div className="min-w-0 flex-1">
              <span className={cn("font-medium", eventColors[event.event_type] ?? "text-muted-foreground")}>
                {event.event_type}
              </span>
              {event.agent_id && (
                <span className="ml-1 text-muted-foreground">
                  ({event.agent_id})
                </span>
              )}
              {event.workflow_id && (
                <span className="ml-1 font-mono text-muted-foreground/60">
                  {event.workflow_id.slice(0, 8)}
                </span>
              )}
            </div>
            {event.timestamp && (
              <span className="shrink-0 text-muted-foreground/50 tabular-nums">
                {new Date(event.timestamp).toLocaleTimeString()}
              </span>
            )}
          </div>
        ))}
      </div>
    </ScrollArea>
  );
}
