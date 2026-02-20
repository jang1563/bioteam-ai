"use client";

import React, { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Plus, Trash2, Pencil, Search } from "lucide-react";
import { TableSkeleton } from "@/components/dashboard/loading-skeletons";
import { useNegativeResults } from "@/hooks/use-negative-results";
import type {
  CreateNegativeResultRequest,
  NegativeResult,
  NRSource,
  UpdateNegativeResultRequest,
} from "@/types/api";

const sourceLabels: Record<NRSource, string> = {
  internal: "Internal",
  clinical_trial: "Clinical Trial",
  shadow: "Shadow",
  preprint_delta: "Preprint Delta",
};

const verificationColors: Record<string, string> = {
  unverified: "secondary",
  confirmed: "default",
  rejected: "destructive",
  ambiguous: "outline",
};

export default function LabKBPage() {
  const [sourceFilter, setSourceFilter] = useState<NRSource | undefined>();
  const [search, setSearch] = useState("");
  const { results, loading, create, update, remove } = useNegativeResults(sourceFilter);

  const filtered = search
    ? results.filter(
        (r) =>
          r.claim.toLowerCase().includes(search.toLowerCase()) ||
          r.outcome.toLowerCase().includes(search.toLowerCase()),
      )
    : results;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">Lab Knowledge Base</h1>
        <CreateNRDialog onCreate={create} />
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <label htmlFor="kb-search" className="sr-only">Search claims and outcomes</label>
          <Input
            id="kb-search"
            placeholder="Search claims & outcomes..."
            className="pl-8"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search claims and outcomes"
          />
        </div>
        <label htmlFor="kb-source-filter" className="sr-only">Filter by source</label>
        <Select
          value={sourceFilter ?? "all"}
          onValueChange={(v) => setSourceFilter(v === "all" ? undefined : (v as NRSource))}
        >
          <SelectTrigger className="w-[160px]" id="kb-source-filter" aria-label="Filter by source">
            <SelectValue placeholder="All Sources" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Sources</SelectItem>
            <SelectItem value="internal">Internal</SelectItem>
            <SelectItem value="clinical_trial">Clinical Trial</SelectItem>
            <SelectItem value="shadow">Shadow</SelectItem>
            <SelectItem value="preprint_delta">Preprint Delta</SelectItem>
          </SelectContent>
        </Select>
        <span className="text-xs text-muted-foreground">
          {filtered.length} results
        </span>
      </div>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <TableSkeleton rows={5} />
          ) : filtered.length === 0 ? (
            <div className="py-12 text-center text-sm text-muted-foreground">
              No negative results found. Add your first entry above.
            </div>
          ) : (
            <Table aria-label="Negative results knowledge base">
              <caption className="sr-only">
                Lab knowledge base negative results. {filtered.length} entries displayed.
              </caption>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[30%]">Claim</TableHead>
                  <TableHead className="w-[30%]">Outcome</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Confidence</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-[80px]"><span className="sr-only">Actions</span></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((nr) => (
                  <NRRow key={nr.id} nr={nr} onUpdate={update} onDelete={remove} />
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function NRRow({
  nr,
  onUpdate,
  onDelete,
}: {
  nr: NegativeResult;
  onUpdate: (id: string, req: UpdateNegativeResultRequest) => Promise<NegativeResult>;
  onDelete: (id: string) => Promise<void>;
}) {
  return (
    <TableRow>
      <TableCell className="text-xs">{nr.claim}</TableCell>
      <TableCell className="text-xs">{nr.outcome}</TableCell>
      <TableCell>
        <Badge variant="outline" className="text-xs">
          {sourceLabels[nr.source as NRSource] ?? nr.source}
        </Badge>
      </TableCell>
      <TableCell className="font-mono text-xs">
        {(nr.confidence * 100).toFixed(0)}%
      </TableCell>
      <TableCell>
        <Badge
          variant={
            (verificationColors[nr.verification_status] ?? "secondary") as
              | "default"
              | "secondary"
              | "destructive"
              | "outline"
          }
          className="text-xs"
        >
          {nr.verification_status}
        </Badge>
      </TableCell>
      <TableCell>
        <div className="flex gap-1">
          <EditNRDialog nr={nr} onUpdate={onUpdate} />
          <Button
            size="icon"
            variant="ghost"
            className="h-7 w-7"
            aria-label={`Delete entry: ${nr.claim.slice(0, 50)}`}
            onClick={() => {
              if (window.confirm(`Delete this entry?\n\nClaim: ${nr.claim}`)) {
                onDelete(nr.id);
              }
            }}
          >
            <Trash2 className="h-3 w-3 text-destructive" aria-hidden="true" />
          </Button>
        </div>
      </TableCell>
    </TableRow>
  );
}

function CreateNRDialog({
  onCreate,
}: {
  onCreate: (req: CreateNegativeResultRequest) => Promise<NegativeResult>;
}) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    claim: "",
    outcome: "",
    source: "internal" as NRSource,
    confidence: "0.5",
    failure_category: "",
    organism: "",
  });
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    if (!form.claim.trim() || !form.outcome.trim()) return;
    setLoading(true);
    try {
      await onCreate({
        claim: form.claim.trim(),
        outcome: form.outcome.trim(),
        source: form.source,
        confidence: parseFloat(form.confidence) || 0.5,
        failure_category: (form.failure_category || undefined) as CreateNegativeResultRequest["failure_category"],
        organism: form.organism || undefined,
      });
      setOpen(false);
      setForm({ claim: "", outcome: "", source: "internal", confidence: "0.5", failure_category: "", organism: "" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus className="mr-1 h-4 w-4" /> Add Entry
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add Negative Result</DialogTitle>
          <DialogDescription>
            Record a negative or unexpected experimental result in the knowledge base.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 pt-2">
          <Field label="Claim (what was expected)" htmlFor="nr-create-claim">
            <Textarea
              id="nr-create-claim"
              value={form.claim}
              onChange={(e) => setForm((f) => ({ ...f, claim: e.target.value }))}
              placeholder="e.g., Drug X inhibits target Y at 10uM"
            />
          </Field>
          <Field label="Outcome (what happened)" htmlFor="nr-create-outcome">
            <Textarea
              id="nr-create-outcome"
              value={form.outcome}
              onChange={(e) => setForm((f) => ({ ...f, outcome: e.target.value }))}
              placeholder="e.g., No inhibition observed"
            />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Source" htmlFor="nr-create-source">
              <Select
                value={form.source}
                onValueChange={(v) => setForm((f) => ({ ...f, source: v as NRSource }))}
              >
                <SelectTrigger id="nr-create-source"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="internal">Internal</SelectItem>
                  <SelectItem value="clinical_trial">Clinical Trial</SelectItem>
                  <SelectItem value="shadow">Shadow</SelectItem>
                  <SelectItem value="preprint_delta">Preprint Delta</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Field label="Confidence" htmlFor="nr-create-confidence">
              <Input
                id="nr-create-confidence"
                type="number"
                min="0"
                max="1"
                step="0.05"
                value={form.confidence}
                onChange={(e) => setForm((f) => ({ ...f, confidence: e.target.value }))}
              />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Failure Category" htmlFor="nr-create-failure-cat">
              <Select
                value={form.failure_category || "none"}
                onValueChange={(v) => setForm((f) => ({ ...f, failure_category: v === "none" ? "" : v }))}
              >
                <SelectTrigger id="nr-create-failure-cat"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  <SelectItem value="protocol">Protocol</SelectItem>
                  <SelectItem value="reagent">Reagent</SelectItem>
                  <SelectItem value="analysis">Analysis</SelectItem>
                  <SelectItem value="biological">Biological</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Field label="Organism" htmlFor="nr-create-organism">
              <Input
                id="nr-create-organism"
                value={form.organism}
                onChange={(e) => setForm((f) => ({ ...f, organism: e.target.value }))}
                placeholder="e.g., Homo sapiens"
              />
            </Field>
          </div>
          <Button onClick={handleSubmit} disabled={loading || !form.claim.trim() || !form.outcome.trim()} className="w-full">
            {loading ? "Adding..." : "Add Entry"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function EditNRDialog({
  nr,
  onUpdate,
}: {
  nr: NegativeResult;
  onUpdate: (id: string, req: UpdateNegativeResultRequest) => Promise<NegativeResult>;
}) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    confidence: String(nr.confidence),
    verification_status: nr.verification_status,
    verified_by: nr.verified_by ?? "",
  });
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    setLoading(true);
    try {
      await onUpdate(nr.id, {
        confidence: parseFloat(form.confidence) || undefined,
        verification_status: form.verification_status as UpdateNegativeResultRequest["verification_status"],
        verified_by: form.verified_by || undefined,
      });
      setOpen(false);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          size="icon"
          variant="ghost"
          className="h-7 w-7"
          aria-label={`Edit entry: ${nr.claim.slice(0, 50)}`}
        >
          <Pencil className="h-3 w-3" aria-hidden="true" />
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit Entry</DialogTitle>
          <DialogDescription>
            Update the confidence, verification status, or reviewer for this entry.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 pt-2">
          <div className="text-xs text-muted-foreground">
            <p><span className="font-medium">Claim:</span> {nr.claim}</p>
            <p className="mt-1"><span className="font-medium">Outcome:</span> {nr.outcome}</p>
          </div>
          <Field label="Confidence" htmlFor="nr-edit-confidence">
            <Input
              id="nr-edit-confidence"
              type="number"
              min="0"
              max="1"
              step="0.05"
              value={form.confidence}
              onChange={(e) => setForm((f) => ({ ...f, confidence: e.target.value }))}
            />
          </Field>
          <Field label="Verification Status" htmlFor="nr-edit-status">
            <Select
              value={form.verification_status}
              onValueChange={(v) => setForm((f) => ({ ...f, verification_status: v as typeof f.verification_status }))}
            >
              <SelectTrigger id="nr-edit-status"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="unverified">Unverified</SelectItem>
                <SelectItem value="confirmed">Confirmed</SelectItem>
                <SelectItem value="rejected">Rejected</SelectItem>
                <SelectItem value="ambiguous">Ambiguous</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field label="Verified By" htmlFor="nr-edit-verified-by">
            <Input
              id="nr-edit-verified-by"
              value={form.verified_by}
              onChange={(e) => setForm((f) => ({ ...f, verified_by: e.target.value }))}
              placeholder="Your name"
            />
          </Field>
          <Button onClick={handleSubmit} disabled={loading} className="w-full">
            {loading ? "Saving..." : "Save Changes"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Field({ label, htmlFor, children }: { label: string; htmlFor?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label htmlFor={htmlFor} className="text-xs font-medium text-muted-foreground">{label}</label>
      {children}
    </div>
  );
}
