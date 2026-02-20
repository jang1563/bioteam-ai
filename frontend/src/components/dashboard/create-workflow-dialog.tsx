"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Plus } from "lucide-react";
import { api } from "@/lib/api-client";
import type { CreateWorkflowResponse } from "@/types/api";

interface Props {
  onCreated?: () => void;
}

export function CreateWorkflowDialog({ onCreated }: Props) {
  const [open, setOpen] = useState(false);
  const [template, setTemplate] = useState("W1");
  const [query, setQuery] = useState("");
  const [budget, setBudget] = useState("5.0");
  const [seedPapers, setSeedPapers] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      await api.post<CreateWorkflowResponse>("/api/v1/workflows", {
        template,
        query: query.trim(),
        budget: parseFloat(budget) || 5.0,
        seed_papers: seedPapers
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean),
      });
      setOpen(false);
      setQuery("");
      setSeedPapers("");
      onCreated?.();
    } catch {
      // handled by API client
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus className="mr-1 h-4 w-4" /> New Workflow
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create Workflow</DialogTitle>
          <DialogDescription>
            Configure and launch a new research workflow.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 pt-2">
          <div className="space-y-1">
            <label htmlFor="workflow-template" className="text-xs font-medium text-muted-foreground">
              Template
            </label>
            <Select value={template} onValueChange={setTemplate}>
              <SelectTrigger id="workflow-template" aria-label="Workflow template">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="W1">W1 — Literature Review</SelectItem>
                <SelectItem value="W2">W2 — Data Analysis</SelectItem>
                <SelectItem value="W3">W3 — Hypothesis Generation</SelectItem>
                <SelectItem value="W4">W4 — Protocol Design</SelectItem>
                <SelectItem value="W5">W5 — Manuscript Draft</SelectItem>
                <SelectItem value="W6">W6 — Grant Proposal</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <label htmlFor="workflow-query" className="text-xs font-medium text-muted-foreground">
              Research Query
            </label>
            <Textarea
              id="workflow-query"
              placeholder="e.g., What are the mechanisms of spaceflight-induced anemia?"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="min-h-[80px]"
            />
          </div>

          <div className="space-y-1">
            <label htmlFor="workflow-budget" className="text-xs font-medium text-muted-foreground">
              Budget ($)
            </label>
            <Input
              id="workflow-budget"
              type="number"
              min="0.1"
              max="100"
              step="0.5"
              value={budget}
              onChange={(e) => setBudget(e.target.value)}
            />
          </div>

          <div className="space-y-1">
            <label htmlFor="workflow-seed-papers" className="text-xs font-medium text-muted-foreground">
              Seed Papers (DOIs, one per line)
            </label>
            <Textarea
              id="workflow-seed-papers"
              placeholder="10.1234/example.2024.001"
              value={seedPapers}
              onChange={(e) => setSeedPapers(e.target.value)}
              className="min-h-[60px] font-mono text-xs"
            />
          </div>

          <Button onClick={handleSubmit} disabled={loading || !query.trim()} className="w-full">
            {loading ? "Creating..." : "Create Workflow"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
