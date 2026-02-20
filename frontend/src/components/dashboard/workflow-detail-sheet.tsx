"use client";

import { useState } from "react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Pause, Play, XCircle, MessageSquarePlus } from "lucide-react";
import { useWorkflowDetail } from "@/hooks/use-workflows";
import { useAppStore } from "@/stores/app-store";
import { api } from "@/lib/api-client";
import type { InterveneResponse, NoteAction } from "@/types/api";

export function WorkflowDetailSheet() {
  const selectedId = useAppStore((s) => s.selectedWorkflowId);
  const setSelected = useAppStore((s) => s.setSelectedWorkflowId);
  const { workflow, loading } = useWorkflowDetail(selectedId);
  const [note, setNote] = useState("");
  const [noteAction, setNoteAction] = useState<NoteAction>("FREE_TEXT");
  const [intervening, setIntervening] = useState(false);

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
    } catch {
      // error handled by API client
    } finally {
      setIntervening(false);
    }
  };

  const budgetUsed = workflow
    ? workflow.budget_total - workflow.budget_remaining
    : 0;
  const budgetPct = workflow && workflow.budget_total > 0
    ? Math.round((budgetUsed / workflow.budget_total) * 100)
    : 0;

  return (
    <Sheet open={!!selectedId} onOpenChange={(open) => !open && setSelected(null)}>
      <SheetContent className="w-[450px] overflow-y-auto sm:max-w-[450px]">
        <SheetHeader>
          <SheetTitle>
            Workflow {workflow?.template ?? ""}
          </SheetTitle>
        </SheetHeader>

        {loading && (
          <p className="py-4 text-sm text-muted-foreground">Loading...</p>
        )}

        {workflow && (
          <div className="mt-4 space-y-4">
            {/* State badge + ID */}
            <div className="flex items-center gap-2">
              <Badge variant="outline">{workflow.state}</Badge>
              <span className="font-mono text-xs text-muted-foreground truncate">
                {workflow.id}
              </span>
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

            {/* Step Timeline */}
            <div>
              <p className="mb-2 text-xs font-medium text-muted-foreground">
                Step History
              </p>
              {workflow.step_history.length === 0 ? (
                <p className="text-xs text-muted-foreground/60">No steps yet</p>
              ) : (
                <div className="space-y-1">
                  {workflow.step_history.map((step, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-2 rounded px-2 py-1 text-xs hover:bg-accent"
                    >
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                      <span className="font-medium">
                        {step.step_id ?? `Step ${i + 1}`}
                      </span>
                      {step.agent_id && (
                        <span className="text-muted-foreground">
                          ({step.agent_id})
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
              {workflow.current_step && (
                <div className="mt-1 flex items-center gap-2 rounded bg-accent px-2 py-1 text-xs">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-blue-500" />
                  <span className="font-medium">{workflow.current_step}</span>
                  <span className="text-muted-foreground">(current)</span>
                </div>
              )}
            </div>

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

            <Separator />

            {/* Intervention Controls */}
            <div>
              <p className="mb-2 text-xs font-medium text-muted-foreground">
                Interventions
              </p>
              <div className="flex gap-2">
                {(workflow.state === "RUNNING" || workflow.state === "WAITING_HUMAN") && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={intervening}
                    onClick={() => doIntervene("pause")}
                  >
                    <Pause className="mr-1 h-3 w-3" /> Pause
                  </Button>
                )}
                {workflow.state === "PAUSED" && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={intervening}
                    onClick={() => doIntervene("resume")}
                  >
                    <Play className="mr-1 h-3 w-3" /> Resume
                  </Button>
                )}
                {["PENDING", "RUNNING", "PAUSED", "WAITING_HUMAN"].includes(workflow.state) && (
                  <Button
                    size="sm"
                    variant="destructive"
                    disabled={intervening}
                    onClick={() => doIntervene("cancel")}
                  >
                    <XCircle className="mr-1 h-3 w-3" /> Cancel
                  </Button>
                )}
              </div>

              {/* Inject Note */}
              <div className="mt-3 space-y-2">
                <Select value={noteAction} onValueChange={(v) => setNoteAction(v as NoteAction)}>
                  <SelectTrigger className="h-8 text-xs">
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
                <Textarea
                  placeholder="Enter note for workflow..."
                  className="min-h-[60px] text-xs"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                />
                <Button
                  size="sm"
                  variant="outline"
                  disabled={intervening || !note.trim()}
                  onClick={() => doIntervene("inject_note")}
                >
                  <MessageSquarePlus className="mr-1 h-3 w-3" /> Inject Note
                </Button>
              </div>
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
