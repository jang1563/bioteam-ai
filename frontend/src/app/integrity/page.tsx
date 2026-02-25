"use client";

import React, { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Search, ShieldCheck, Play, Trash2 } from "lucide-react";
import { TableSkeleton } from "@/components/dashboard/loading-skeletons";
import { useIntegrityFindings, useIntegrityStats } from "@/hooks/use-integrity";
import { IntegrityDetailSheet } from "@/components/dashboard/integrity-detail-sheet";
import type {
  AuditFinding,
  FindingStatus,
  IntegritySeverity,
  TriggerAuditRequest,
  UpdateFindingRequest,
} from "@/types/api";

const severityColors: Record<IntegritySeverity, string> = {
  critical: "destructive",
  error: "destructive",
  warning: "default",
  info: "secondary",
};

const statusColors: Record<FindingStatus, string> = {
  open: "destructive",
  acknowledged: "default",
  resolved: "secondary",
  false_positive: "outline",
};

const categoryLabels: Record<string, string> = {
  gene_name_error: "Gene Name",
  statistical_inconsistency: "Statistics",
  retracted_reference: "Retracted",
  corrected_reference: "Corrected",
  pubpeer_flagged: "PubPeer",
  metadata_error: "Metadata",
  sample_size_mismatch: "Sample Size",
  genome_build_inconsistency: "Genome Build",
  p_value_mismatch: "P-value",
  benford_anomaly: "Benford",
  grim_failure: "GRIM",
};

export default function IntegrityPage() {
  const [severityFilter, setSeverityFilter] = useState<IntegritySeverity | undefined>();
  const [statusFilter, setStatusFilter] = useState<FindingStatus | undefined>();
  const [search, setSearch] = useState("");
  const [selectedFinding, setSelectedFinding] = useState<AuditFinding | null>(null);

  const { findings, loading, updateFinding, deleteFinding, triggerAudit } =
    useIntegrityFindings({
      severity: severityFilter,
      status: statusFilter,
    });
  const { stats } = useIntegrityStats();

  const filtered = search
    ? findings.filter(
        (f) =>
          f.title.toLowerCase().includes(search.toLowerCase()) ||
          f.description.toLowerCase().includes(search.toLowerCase()) ||
          f.category.toLowerCase().includes(search.toLowerCase()),
      )
    : findings;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <ShieldCheck className="h-6 w-6 text-primary" aria-hidden="true" />
          <h1 className="text-2xl font-bold tracking-tight">Data Integrity</h1>
        </div>
        <TriggerAuditDialog onTrigger={triggerAudit} />
      </div>

      {/* Stats summary */}
      {stats && stats.total_findings > 0 && (
        <div className="flex flex-wrap gap-3">
          {Object.entries(stats.findings_by_severity).map(([sev, count]) => (
            <Badge
              key={sev}
              variant={severityColors[sev as IntegritySeverity] as "default" | "secondary" | "destructive" | "outline"}
              className="text-xs"
            >
              {sev}: {count}
            </Badge>
          ))}
          <span className="text-xs text-muted-foreground">
            {stats.total_runs} runs | avg {stats.average_findings_per_run.toFixed(1)}/run
          </span>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <label htmlFor="integrity-search" className="sr-only">Search findings</label>
          <Input
            id="integrity-search"
            placeholder="Search findings..."
            className="pl-8"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search integrity findings"
          />
        </div>
        <label htmlFor="severity-filter" className="sr-only">Filter by severity</label>
        <Select
          value={severityFilter ?? "all"}
          onValueChange={(v) => setSeverityFilter(v === "all" ? undefined : (v as IntegritySeverity))}
        >
          <SelectTrigger className="w-[140px]" id="severity-filter" aria-label="Filter by severity">
            <SelectValue placeholder="All Severity" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Severity</SelectItem>
            <SelectItem value="critical">Critical</SelectItem>
            <SelectItem value="error">Error</SelectItem>
            <SelectItem value="warning">Warning</SelectItem>
            <SelectItem value="info">Info</SelectItem>
          </SelectContent>
        </Select>
        <label htmlFor="status-filter" className="sr-only">Filter by status</label>
        <Select
          value={statusFilter ?? "all"}
          onValueChange={(v) => setStatusFilter(v === "all" ? undefined : (v as FindingStatus))}
        >
          <SelectTrigger className="w-[160px]" id="status-filter" aria-label="Filter by status">
            <SelectValue placeholder="All Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Status</SelectItem>
            <SelectItem value="open">Open</SelectItem>
            <SelectItem value="acknowledged">Acknowledged</SelectItem>
            <SelectItem value="resolved">Resolved</SelectItem>
            <SelectItem value="false_positive">False Positive</SelectItem>
          </SelectContent>
        </Select>
        <span className="text-xs text-muted-foreground">
          {filtered.length} findings
        </span>
      </div>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <TableSkeleton rows={5} />
          ) : filtered.length === 0 ? (
            <div className="py-12 text-center text-sm text-muted-foreground">
              No integrity findings. Run an audit to check for data issues.
            </div>
          ) : (
            <Table aria-label="Data integrity findings">
              <caption className="sr-only">
                Data integrity findings. {filtered.length} entries displayed.
              </caption>
              <TableHeader>
                <TableRow>
                  <TableHead>Severity</TableHead>
                  <TableHead className="w-[25%]">Title</TableHead>
                  <TableHead>Category</TableHead>
                  <TableHead>Confidence</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-[80px]"><span className="sr-only">Actions</span></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((f) => (
                  <FindingRow
                    key={f.id}
                    finding={f}
                    onSelect={() => setSelectedFinding(f)}
                    onUpdate={updateFinding}
                    onDelete={deleteFinding}
                  />
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Detail sheet */}
      <IntegrityDetailSheet
        finding={selectedFinding}
        onClose={() => setSelectedFinding(null)}
        onUpdate={updateFinding}
      />
    </div>
  );
}

function FindingRow({
  finding,
  onSelect,
  onUpdate,
  onDelete,
}: {
  finding: AuditFinding;
  onSelect: () => void;
  onUpdate: (id: string, req: UpdateFindingRequest) => Promise<AuditFinding>;
  onDelete: (id: string) => Promise<void>;
}) {
  return (
    <TableRow className="cursor-pointer" onClick={onSelect}>
      <TableCell>
        <Badge
          variant={severityColors[finding.severity as IntegritySeverity] as "default" | "secondary" | "destructive" | "outline"}
          className="text-xs"
        >
          {finding.severity}
        </Badge>
      </TableCell>
      <TableCell className="text-xs font-medium">{finding.title}</TableCell>
      <TableCell>
        <Badge variant="outline" className="text-xs">
          {categoryLabels[finding.category] ?? finding.category}
        </Badge>
      </TableCell>
      <TableCell className="font-mono text-xs">
        {(finding.confidence * 100).toFixed(0)}%
      </TableCell>
      <TableCell>
        <Badge
          variant={statusColors[finding.status as FindingStatus] as "default" | "secondary" | "destructive" | "outline"}
          className="text-xs"
        >
          {finding.status}
        </Badge>
      </TableCell>
      <TableCell>
        <Button
          size="icon"
          variant="ghost"
          className="h-7 w-7"
          aria-label={`Delete finding: ${finding.title}`}
          onClick={(e) => {
            e.stopPropagation();
            if (window.confirm(`Delete this finding?\n\n${finding.title}`)) {
              onDelete(finding.id);
            }
          }}
        >
          <Trash2 className="h-3 w-3 text-destructive" aria-hidden="true" />
        </Button>
      </TableCell>
    </TableRow>
  );
}

function TriggerAuditDialog({
  onTrigger,
}: {
  onTrigger: (req: TriggerAuditRequest) => Promise<unknown>;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    if (!text.trim()) return;
    setLoading(true);
    try {
      await onTrigger({ text: text.trim(), use_llm: false });
      setOpen(false);
      setText("");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Play className="mr-1 h-4 w-4" /> Run Audit
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Run Integrity Audit</DialogTitle>
          <DialogDescription>
            Paste text from a paper or dataset to check for data integrity issues
            (gene name errors, statistical inconsistencies, retracted references).
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 pt-2">
          <label htmlFor="audit-text" className="text-xs font-medium text-muted-foreground">
            Text to analyze
          </label>
          <Textarea
            id="audit-text"
            rows={8}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Paste text from a paper, supplementary table, or dataset description..."
          />
          <Button
            onClick={handleSubmit}
            disabled={loading || !text.trim()}
            className="w-full"
          >
            {loading ? "Running audit..." : "Run Quick Check"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
