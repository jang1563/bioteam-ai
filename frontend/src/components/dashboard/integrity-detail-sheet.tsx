"use client";

import React, { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import type { AuditFinding, FindingStatus, IntegritySeverity, UpdateFindingRequest } from "@/types/api";

const severityColors: Record<IntegritySeverity, string> = {
  critical: "destructive",
  error: "destructive",
  warning: "default",
  info: "secondary",
};

interface IntegrityDetailSheetProps {
  finding: AuditFinding | null;
  onClose: () => void;
  onUpdate: (id: string, req: UpdateFindingRequest) => Promise<AuditFinding>;
}

export function IntegrityDetailSheet({ finding, onClose, onUpdate }: IntegrityDetailSheetProps) {
  const [newStatus, setNewStatus] = useState<FindingStatus>("open");
  const [resolvedBy, setResolvedBy] = useState("");
  const [resolutionNote, setResolutionNote] = useState("");
  const [saving, setSaving] = useState(false);

  // Reset form when finding changes
  React.useEffect(() => {
    if (finding) {
      setNewStatus(finding.status as FindingStatus);
      setResolvedBy(finding.resolved_by ?? "");
      setResolutionNote(finding.resolution_note ?? "");
    }
  }, [finding]);

  const handleSave = async () => {
    if (!finding) return;
    setSaving(true);
    try {
      await onUpdate(finding.id, {
        status: newStatus,
        resolved_by: resolvedBy || undefined,
        resolution_note: resolutionNote || undefined,
      });
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <Sheet open={!!finding} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-[450px] overflow-y-auto sm:max-w-[450px]">
        {finding && (
          <>
            <SheetHeader>
              <div className="flex items-center gap-2">
                <Badge
                  variant={severityColors[finding.severity as IntegritySeverity] as "default" | "secondary" | "destructive" | "outline"}
                >
                  {finding.severity}
                </Badge>
                <Badge variant="outline">{finding.category}</Badge>
              </div>
              <SheetTitle className="text-lg">{finding.title}</SheetTitle>
              <SheetDescription>{finding.description}</SheetDescription>
            </SheetHeader>

            <div className="mt-6 space-y-4">
              {/* Source text */}
              {finding.source_text && (
                <div>
                  <h4 className="text-xs font-medium text-muted-foreground mb-1">Source Text</h4>
                  <pre className="rounded-md bg-muted p-3 text-xs whitespace-pre-wrap">
                    {finding.source_text}
                  </pre>
                </div>
              )}

              {/* Suggestion */}
              {finding.suggestion && (
                <div>
                  <h4 className="text-xs font-medium text-muted-foreground mb-1">Suggestion</h4>
                  <p className="text-sm">{finding.suggestion}</p>
                </div>
              )}

              <Separator />

              {/* Details grid */}
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <span className="text-xs text-muted-foreground">Confidence</span>
                  <p className="font-mono">{(finding.confidence * 100).toFixed(0)}%</p>
                </div>
                <div>
                  <span className="text-xs text-muted-foreground">Checker</span>
                  <p>{finding.checker || "N/A"}</p>
                </div>
                {finding.paper_doi && (
                  <div className="col-span-2">
                    <span className="text-xs text-muted-foreground">DOI</span>
                    <p className="font-mono text-xs">{finding.paper_doi}</p>
                  </div>
                )}
                {finding.workflow_id && (
                  <div className="col-span-2">
                    <span className="text-xs text-muted-foreground">Workflow</span>
                    <p className="font-mono text-xs">{finding.workflow_id}</p>
                  </div>
                )}
                <div>
                  <span className="text-xs text-muted-foreground">Created</span>
                  <p className="text-xs">{new Date(finding.created_at).toLocaleString()}</p>
                </div>
                <div>
                  <span className="text-xs text-muted-foreground">Updated</span>
                  <p className="text-xs">{new Date(finding.updated_at).toLocaleString()}</p>
                </div>
              </div>

              {/* Finding metadata */}
              {finding.finding_metadata && Object.keys(finding.finding_metadata).length > 0 && (
                <div>
                  <h4 className="text-xs font-medium text-muted-foreground mb-1">Metadata</h4>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    {Object.entries(finding.finding_metadata).map(([key, value]) => (
                      <div key={key}>
                        <span className="text-muted-foreground">{key}</span>
                        <p className="font-mono">{String(value)}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <Separator />

              {/* Resolution form */}
              <div className="space-y-3">
                <h4 className="text-sm font-medium">Resolution</h4>
                <div className="space-y-1">
                  <label htmlFor="finding-status" className="text-xs text-muted-foreground">Status</label>
                  <Select
                    value={newStatus}
                    onValueChange={(v) => setNewStatus(v as FindingStatus)}
                  >
                    <SelectTrigger id="finding-status"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="open">Open</SelectItem>
                      <SelectItem value="acknowledged">Acknowledged</SelectItem>
                      <SelectItem value="resolved">Resolved</SelectItem>
                      <SelectItem value="false_positive">False Positive</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <label htmlFor="finding-resolved-by" className="text-xs text-muted-foreground">Resolved By</label>
                  <Input
                    id="finding-resolved-by"
                    value={resolvedBy}
                    onChange={(e) => setResolvedBy(e.target.value)}
                    placeholder="Your name"
                  />
                </div>
                <div className="space-y-1">
                  <label htmlFor="finding-note" className="text-xs text-muted-foreground">Resolution Note</label>
                  <Textarea
                    id="finding-note"
                    rows={3}
                    value={resolutionNote}
                    onChange={(e) => setResolutionNote(e.target.value)}
                    placeholder="Explain the resolution or why this is a false positive..."
                  />
                </div>
                <Button onClick={handleSave} disabled={saving} className="w-full">
                  {saving ? "Saving..." : "Save Changes"}
                </Button>
              </div>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
