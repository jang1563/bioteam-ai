"use client";

import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { useManuscriptSessions } from "@/hooks/use-manuscript-sessions";
import type { ManuscriptSession, WorkflowStatus } from "@/types/api";
import {
  AlertTriangle,
  BookOpen,
  Copy,
  Dna,
  Download,
  FileSearch,
  Link2,
  Loader2,
  Printer,
  RefreshCcw,
  ShieldCheck,
} from "lucide-react";

const TIER_OPTIONS = [
  { value: "nature_cell", label: "Top-tier (Nature / Science / Cell)" },
  { value: "specialty", label: "Specialty (field-specific journals)" },
  { value: "grant", label: "Grant proposal narrative" },
] as const;

const CAPABILITY_LANES = [
  {
    title: "Validated Core",
    badgeClass: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700",
    items: ["Reviewer Risks (W8)", "Submission Checks (W7)"],
    detail: "Benchmark-backed and audit-backed surfaces provide the strongest basis for public technical review.",
  },
  {
    title: "Guided Support",
    badgeClass: "border-blue-500/40 bg-blue-500/10 text-blue-700",
    items: ["Story Frames", "Claim Map"],
    detail: "Useful manuscript-shaping layers that strengthen judgment, but should not carry the main proof claim alone.",
  },
  {
    title: "Research Preview",
    badgeClass: "border-slate-400/40 bg-slate-400/10 text-slate-700",
    items: ["Broader workflow linking", "Extended surfaces"],
    detail: "Keep visible for long-term upside, but secondary to the manuscript-defense core in external reviews.",
  },
] as const;

interface ManuscriptStudioWorkspaceProps {
  workflows: WorkflowStatus[];
}

function phaseLabel(phase: string): string {
  switch (phase) {
    case "collect_inputs":
      return "Collect inputs";
    case "select_frame":
      return "Select frame";
    case "review_claims":
      return "Review claims";
    case "defense_checks":
      return "Defense checks";
    case "outline_ready":
      return "Outline ready";
    default:
      return phase.replaceAll("_", " ");
  }
}

function severityBadgeClass(severity: string): string {
  if (severity === "high" || severity === "critical" || severity === "error" || severity === "failed") {
    return "border-red-500/40 bg-red-500/10 text-red-600";
  }
  if (severity === "medium" || severity === "warning" || severity === "waiting_human" || severity === "partial") {
    return "border-amber-500/40 bg-amber-500/10 text-amber-700";
  }
  if (severity === "running") {
    return "border-blue-500/40 bg-blue-500/10 text-blue-700";
  }
  if (severity === "not_started") {
    return "border-slate-400/40 bg-slate-400/10 text-slate-700";
  }
  return "border-emerald-500/40 bg-emerald-500/10 text-emerald-700";
}

function maturityBadgeClass(maturity: string): string {
  if (maturity === "validated_core") {
    return "border-emerald-500/40 bg-emerald-500/10 text-emerald-700";
  }
  if (maturity === "guided_support") {
    return "border-blue-500/40 bg-blue-500/10 text-blue-700";
  }
  return "border-slate-400/40 bg-slate-400/10 text-slate-700";
}

function maturityLabel(maturity: string): string {
  if (maturity === "validated_core") return "Validated Core";
  if (maturity === "guided_support") return "Guided Support";
  return "Research Preview";
}

export function ManuscriptStudioWorkspace({ workflows }: ManuscriptStudioWorkspaceProps) {
  const {
    sessions,
    loading,
    error,
    create,
    linkWorkflow,
    selectFrame,
    refreshSession,
    runStoryFrames,
    runSubmissionChecks,
    approveStoryScope,
    runReviewerRisks,
    resumeReviewerRisks,
    uploadReviewerPaper,
    runFullSubmissionAudit,
    getDefenseBrief,
    getDefenseBriefPrint,
    getDefenseBriefDocx,
  } = useManuscriptSessions();
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [query, setQuery] = useState("");
  const [notes, setNotes] = useState("");
  const [draftText, setDraftText] = useState("");
  const [targetJournal, setTargetJournal] = useState("");
  const [workflowToLink, setWorkflowToLink] = useState("");
  const [creating, setCreating] = useState(false);
  const [linking, setLinking] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [runningStoryFrames, setRunningStoryFrames] = useState(false);
  const [runningSubmissionChecks, setRunningSubmissionChecks] = useState(false);
  const [runningFullSubmissionAudit, setRunningFullSubmissionAudit] = useState(false);
  const [exportingDefenseBrief, setExportingDefenseBrief] = useState(false);
  const [exportingDefenseBriefDocx, setExportingDefenseBriefDocx] = useState(false);
  const [printingDefenseBrief, setPrintingDefenseBrief] = useState(false);
  const [copiedDefenseBrief, setCopiedDefenseBrief] = useState(false);
  const [runningReviewerRisks, setRunningReviewerRisks] = useState(false);
  const [uploadingReviewerPaper, setUploadingReviewerPaper] = useState(false);
  const [resumingReviewerRisks, setResumingReviewerRisks] = useState(false);
  const [approvingStoryScope, setApprovingStoryScope] = useState(false);
  const [selectedStoryTier, setSelectedStoryTier] = useState<(typeof TIER_OPTIONS)[number]["value"]>("specialty");
  const [submittingFrameId, setSubmittingFrameId] = useState<string | null>(null);
  const [reviewerPdfPath, setReviewerPdfPath] = useState("");
  const [uploadedReviewerFileName, setUploadedReviewerFileName] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const reviewerUploadRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!selectedSessionId && sessions.length > 0) {
      setSelectedSessionId(sessions[0].id);
    }
  }, [selectedSessionId, sessions]);

  useEffect(() => {
    if (selectedSessionId && !sessions.some((item) => item.id === selectedSessionId)) {
      setSelectedSessionId(sessions[0]?.id ?? null);
    }
  }, [selectedSessionId, sessions]);

  useEffect(() => {
    setSelectedStoryTier("specialty");
    setSubmittingFrameId(null);
    setReviewerPdfPath("");
    setUploadedReviewerFileName("");
  }, [selectedSessionId]);

  const selectedSession = sessions.find((item) => item.id === selectedSessionId) ?? null;
  const linkableWorkflows = [...workflows]
    .filter((wf) => ["W11", "W8", "W7", "W1", "W6"].includes(wf.template))
    .sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""));
  const storyFramesStage = selectedSession?.stage_statuses.find((item) => item.stage === "story_frames") ?? null;
  const reviewerRisksStage = selectedSession?.stage_statuses.find((item) => item.stage === "reviewer_risks") ?? null;
  const submissionChecksStage = selectedSession?.stage_statuses.find((item) => item.stage === "submission_checks") ?? null;
  const storyFramesWaitingForScope = Boolean(
    storyFramesStage &&
      storyFramesStage.status === "waiting_human" &&
      selectedSession &&
      selectedSession.frame_options.length === 0,
  );
  const storyFramesWaitingForSelection = Boolean(
    storyFramesStage &&
      storyFramesStage.status === "waiting_human" &&
      selectedSession &&
      selectedSession.frame_options.length > 0,
  );
  const reviewerRisksWaitingForReview = Boolean(
    reviewerRisksStage &&
      reviewerRisksStage.status === "waiting_human" &&
      selectedSession?.linked_workflows.W8,
  );

  const handleCreate = async () => {
    if (!query.trim()) {
      setActionError("Add a research question or manuscript objective first.");
      return;
    }
    setCreating(true);
    setActionError(null);
    try {
      const created = await create({
        title: title.trim() || undefined,
        query: query.trim(),
        notes: notes.trim() || undefined,
        draft_text: draftText.trim() || undefined,
        target_journal: targetJournal.trim() || undefined,
      });
      setSelectedSessionId(created.id);
      setTitle("");
      setQuery("");
      setNotes("");
      setDraftText("");
      setTargetJournal("");
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to create manuscript session");
    } finally {
      setCreating(false);
    }
  };

  const handleLinkWorkflow = async () => {
    if (!selectedSession || !workflowToLink) return;
    setLinking(true);
    setActionError(null);
    try {
      const updated = await linkWorkflow(selectedSession.id, { workflow_id: workflowToLink });
      setSelectedSessionId(updated.id);
      setWorkflowToLink("");
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to link workflow");
    } finally {
      setLinking(false);
    }
  };

  const handleSelectFrame = async (session: ManuscriptSession, frameId: string) => {
    setSubmittingFrameId(frameId);
    setActionError(null);
    try {
      await selectFrame(session.id, { frame_id: frameId });
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to select story frame");
    } finally {
      setSubmittingFrameId(null);
    }
  };

  const handleRefreshSession = async () => {
    if (!selectedSession) return;
    setRefreshing(true);
    setActionError(null);
    try {
      await refreshSession(selectedSession.id);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to refresh manuscript session");
    } finally {
      setRefreshing(false);
    }
  };

  const handleRunStoryFrames = async () => {
    if (!selectedSession) return;
    setRunningStoryFrames(true);
    setActionError(null);
    try {
      await runStoryFrames(selectedSession.id);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to start story frames");
    } finally {
      setRunningStoryFrames(false);
    }
  };

  const handleRunSubmissionChecks = async () => {
    if (!selectedSession) return;
    setRunningSubmissionChecks(true);
    setActionError(null);
    try {
      await runSubmissionChecks(selectedSession.id);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to run submission checks");
    } finally {
      setRunningSubmissionChecks(false);
    }
  };

  const handleApproveStoryScope = async () => {
    if (!selectedSession) return;
    setApprovingStoryScope(true);
    setActionError(null);
    try {
      await approveStoryScope(selectedSession.id, { target_tier: selectedStoryTier });
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to approve story scope");
    } finally {
      setApprovingStoryScope(false);
    }
  };

  const handleRunFullSubmissionAudit = async () => {
    if (!selectedSession) return;
    setRunningFullSubmissionAudit(true);
    setActionError(null);
    try {
      await runFullSubmissionAudit(selectedSession.id);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to start full submission audit");
    } finally {
      setRunningFullSubmissionAudit(false);
    }
  };

  const handleCopyDefenseBrief = async () => {
    if (!selectedSession) return;
    setExportingDefenseBrief(true);
    setActionError(null);
    try {
      const brief = await getDefenseBrief(selectedSession.id);
      await navigator.clipboard.writeText(brief.markdown);
      setCopiedDefenseBrief(true);
      window.setTimeout(() => setCopiedDefenseBrief(false), 2000);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to copy defense brief");
    } finally {
      setExportingDefenseBrief(false);
    }
  };

  const handleDownloadDefenseBrief = async () => {
    if (!selectedSession) return;
    setExportingDefenseBrief(true);
    setActionError(null);
    try {
      const brief = await getDefenseBrief(selectedSession.id);
      const blob = new Blob([brief.markdown], { type: "text/markdown" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = brief.filename;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to download defense brief");
    } finally {
      setExportingDefenseBrief(false);
    }
  };

  const handlePrintDefenseBrief = async () => {
    if (!selectedSession) return;
    const printWindow = window.open("", "_blank");
    if (!printWindow) {
      setActionError("Allow pop-ups to open the print view for this brief.");
      return;
    }

    printWindow.document.write("<title>Preparing defense brief...</title><p>Preparing print view...</p>");
    setPrintingDefenseBrief(true);
    setActionError(null);
    try {
      const brief = await getDefenseBriefPrint(selectedSession.id);
      printWindow.document.open();
      printWindow.document.write(brief.html);
      printWindow.document.close();
      printWindow.focus();
    } catch (e) {
      printWindow.close();
      setActionError(e instanceof Error ? e.message : "Failed to open print view");
    } finally {
      setPrintingDefenseBrief(false);
    }
  };

  const handleDownloadDefenseBriefDocx = async () => {
    if (!selectedSession) return;
    setExportingDefenseBriefDocx(true);
    setActionError(null);
    try {
      const brief = await getDefenseBriefDocx(selectedSession.id);
      const binary = window.atob(brief.content_base64);
      const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
      const blob = new Blob([bytes], { type: brief.mime_type });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = brief.filename;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to download defense brief DOCX");
    } finally {
      setExportingDefenseBriefDocx(false);
    }
  };

  const handleRunReviewerRisks = async () => {
    if (!selectedSession || !reviewerPdfPath.trim()) {
      setActionError("Add a local manuscript PDF path before starting reviewer risks.");
      return;
    }
    setRunningReviewerRisks(true);
    setActionError(null);
    try {
      await runReviewerRisks(selectedSession.id, { pdf_path: reviewerPdfPath.trim() });
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to start reviewer risks");
    } finally {
      setRunningReviewerRisks(false);
    }
  };

  const handleResumeReviewerRisks = async () => {
    if (!selectedSession) return;
    setResumingReviewerRisks(true);
    setActionError(null);
    try {
      await resumeReviewerRisks(selectedSession.id);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to resume reviewer risks");
    } finally {
      setResumingReviewerRisks(false);
    }
  };

  const handleUploadReviewerPaper = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || !selectedSession) return;
    setUploadingReviewerPaper(true);
    setActionError(null);
    setUploadedReviewerFileName(file.name);
    try {
      await uploadReviewerPaper(selectedSession.id, file);
      setReviewerPdfPath("");
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to upload reviewer paper");
    } finally {
      setUploadingReviewerPaper(false);
      if (event.target) {
        event.target.value = "";
      }
    }
  };

  return (
    <section className="space-y-4" id="workspace">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Session Workspace</h2>
        <p className="text-sm text-muted-foreground">
          Create a manuscript session, start or link W11/W8/W7 runs, and keep story, evidence, reviewer
          pressure, and submission checks in one place.
        </p>
      </div>

      <div className="grid gap-3 xl:grid-cols-3">
        {CAPABILITY_LANES.map((lane) => (
          <Card key={lane.title} className="border-border/70">
            <CardContent className="space-y-3 pt-4">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-medium">{lane.title}</p>
                <Badge variant="outline" className={lane.badgeClass}>
                  {lane.title}
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground">{lane.detail}</p>
              <div className="flex flex-wrap gap-2">
                {lane.items.map((item) => (
                  <Badge key={item} variant="outline" className="text-[10px]">
                    {item}
                  </Badge>
                ))}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">New Session</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1.5">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Title</p>
              <Input
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="Spaceflight anemia manuscript"
              />
            </div>
            <div className="space-y-1.5">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Research question</p>
              <Textarea
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="What is the strongest, most defensible story for this dataset?"
                className="min-h-20"
              />
            </div>
            <div className="space-y-1.5">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Notes</p>
              <Textarea
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                placeholder="Target journal, audience, known reviewer concerns, or framing constraints."
                className="min-h-20"
              />
            </div>
            <div className="space-y-1.5">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Draft excerpt</p>
              <Textarea
                value={draftText}
                onChange={(event) => setDraftText(event.target.value)}
                placeholder="Optional excerpt or abstract to anchor the session."
                className="min-h-24"
              />
            </div>
            <div className="space-y-1.5">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Target journal</p>
              <Input
                value={targetJournal}
                onChange={(event) => setTargetJournal(event.target.value)}
                placeholder="Nature Communications"
              />
            </div>
            <Button className="w-full gap-2" onClick={handleCreate} disabled={creating}>
              {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <BookOpen className="h-4 w-4" />}
              Create manuscript session
            </Button>
            <Separator />
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Sessions</p>
                {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" /> : null}
              </div>
              {sessions.length === 0 ? (
                <p className="text-sm text-muted-foreground">No manuscript sessions yet.</p>
              ) : (
                <div className="space-y-2">
                  {sessions.map((session) => (
                    <button
                      type="button"
                      key={session.id}
                      onClick={() => setSelectedSessionId(session.id)}
                      className={`w-full rounded-lg border p-3 text-left transition-colors ${
                        session.id === selectedSessionId
                          ? "border-primary bg-primary/5"
                          : "border-border hover:border-primary/40"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <p className="text-sm font-medium">{session.title}</p>
                          <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{session.query}</p>
                        </div>
                        <Badge variant="outline">{phaseLabel(session.phase)}</Badge>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
            {(error || actionError) && (
              <div className="rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-700">
                {actionError ?? error}
              </div>
            )}
          </CardContent>
        </Card>

        <div className="space-y-4">
          {!selectedSession ? (
            <Card className="border-dashed">
              <CardContent className="py-12 text-center text-sm text-muted-foreground">
                Create a manuscript session to start linking workflows and building a defense-ready outline.
              </CardContent>
            </Card>
          ) : (
            <>
              <Card>
                <CardHeader className="pb-3">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <CardTitle className="text-base">{selectedSession.title}</CardTitle>
                      <p className="mt-1 text-sm text-muted-foreground">{selectedSession.query}</p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline">{phaseLabel(selectedSession.phase)}</Badge>
                      <Badge variant={selectedSession.completion_state === "ready" ? "default" : "outline"}>
                        {selectedSession.completion_state}
                      </Badge>
                      <Button variant="outline" size="sm" className="gap-2" onClick={handleRefreshSession} disabled={refreshing}>
                        {refreshing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCcw className="h-3.5 w-3.5" />}
                        Refresh
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="gap-2"
                        onClick={handleCopyDefenseBrief}
                        disabled={exportingDefenseBrief}
                      >
                        {exportingDefenseBrief ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Copy className="h-3.5 w-3.5" />}
                        {copiedDefenseBrief ? "Copied" : "Copy Brief"}
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="gap-2"
                        onClick={handleDownloadDefenseBrief}
                        disabled={exportingDefenseBrief}
                      >
                        {exportingDefenseBrief ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                        Download Brief
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="gap-2"
                        onClick={handlePrintDefenseBrief}
                        disabled={printingDefenseBrief}
                      >
                        {printingDefenseBrief ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Printer className="h-3.5 w-3.5" />}
                        Print / Save PDF
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="gap-2"
                        onClick={handleDownloadDefenseBriefDocx}
                        disabled={exportingDefenseBriefDocx}
                      >
                        {exportingDefenseBriefDocx ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                        Download DOCX
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto]">
                    <Select value={workflowToLink} onValueChange={setWorkflowToLink}>
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder="Link an existing W11, W8, W7, W1, or W6 workflow" />
                      </SelectTrigger>
                      <SelectContent>
                        {linkableWorkflows.map((workflow) => (
                          <SelectItem key={workflow.id} value={workflow.id}>
                            {workflow.template} · {workflow.query.slice(0, 70)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button variant="outline" className="gap-2" onClick={handleLinkWorkflow} disabled={!workflowToLink || linking}>
                      {linking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Link2 className="h-4 w-4" />}
                      Link workflow
                    </Button>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    <Button className="gap-2" onClick={handleRunStoryFrames} disabled={runningStoryFrames}>
                      {runningStoryFrames ? <Loader2 className="h-4 w-4 animate-spin" /> : <BookOpen className="h-4 w-4" />}
                      Start Story Frames
                    </Button>
                    <Button
                      variant="outline"
                      className="gap-2"
                      onClick={handleRunSubmissionChecks}
                      disabled={runningSubmissionChecks || (!selectedSession.draft_text.trim() && !selectedSession.notes.trim())}
                    >
                      {runningSubmissionChecks ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
                      Quick Draft Scan
                    </Button>
                    <Button
                      className="gap-2"
                      onClick={handleRunFullSubmissionAudit}
                      disabled={runningFullSubmissionAudit || (!selectedSession.query.trim() && !selectedSession.draft_text.trim() && !selectedSession.notes.trim())}
                    >
                      {runningFullSubmissionAudit ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
                      Full Submission Audit
                    </Button>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    {Object.entries(selectedSession.linked_workflows).length === 0 ? (
                      <p className="text-sm text-muted-foreground">No workflows linked yet.</p>
                    ) : (
                      Object.entries(selectedSession.linked_workflows).map(([template, workflowId]) => (
                        <Badge key={workflowId} variant="outline">
                          {template}: {workflowId.slice(0, 8)}
                        </Badge>
                      ))
                    )}
                  </div>

                  <div className="grid gap-3 lg:grid-cols-2">
                    {selectedSession.stage_statuses.map((stage) => (
                      <div key={stage.stage} className="rounded-lg border p-3">
                        <div className="flex items-start justify-between gap-2">
                          <p className="text-sm font-medium capitalize">{stage.stage.replaceAll("_", " ")}</p>
                          <Badge className={severityBadgeClass(stage.status)} variant="outline">
                            {stage.status.replaceAll("_", " ")}
                          </Badge>
                        </div>
                        <p className="mt-2 text-sm text-muted-foreground">{stage.detail}</p>
                        {stage.source_workflow_id ? (
                          <p className="mt-2 text-xs text-muted-foreground">
                            Source workflow: {stage.source_workflow_id.slice(0, 8)}
                          </p>
                        ) : null}
                      </div>
                    ))}
                  </div>

                  {selectedSession.fallback_flags.length > 0 ? (
                    <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3">
                      <div className="mb-2 flex items-center gap-2 text-sm font-medium text-amber-800">
                        <AlertTriangle className="h-4 w-4" />
                        Visible fallbacks
                      </div>
                      <div className="space-y-2">
                        {selectedSession.fallback_flags.map((flag, idx) => (
                          <p key={`${flag.stage}-${idx}`} className="text-sm text-amber-900/90">
                            <span className="font-medium">{flag.stage}:</span> {flag.detail}
                          </p>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </CardContent>
              </Card>

              <div className="grid gap-4 2xl:grid-cols-2">
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-base">
                      <BookOpen className="h-4 w-4 text-primary" />
                      Story Frames
                      <Badge variant="outline" className="ml-auto border-blue-500/40 bg-blue-500/10 text-blue-700">
                        Guided Support
                      </Badge>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {storyFramesWaitingForScope ? (
                      <div className="space-y-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
                        <div>
                          <p className="text-sm font-medium">Approve scope and choose the target tier</p>
                          <p className="mt-1 text-sm text-muted-foreground">{storyFramesStage?.detail}</p>
                        </div>
                        <div className="space-y-1.5">
                          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Target tier</p>
                          <Select value={selectedStoryTier} onValueChange={(value) => setSelectedStoryTier(value as (typeof TIER_OPTIONS)[number]["value"])}>
                            <SelectTrigger className="w-full">
                              <SelectValue placeholder="Choose the manuscript tier" />
                            </SelectTrigger>
                            <SelectContent>
                              {TIER_OPTIONS.map((option) => (
                                <SelectItem key={option.value} value={option.value}>
                                  {option.label}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                        <Button className="gap-2" onClick={handleApproveStoryScope} disabled={approvingStoryScope}>
                          {approvingStoryScope ? <Loader2 className="h-4 w-4 animate-spin" /> : <BookOpen className="h-4 w-4" />}
                          Approve Scope & Generate Frames
                        </Button>
                      </div>
                    ) : selectedSession.frame_options.length === 0 ? (
                      <p className="text-sm text-muted-foreground">Link or start a W11 workflow to populate story frames.</p>
                    ) : (
                      selectedSession.frame_options.map((frame) => {
                        const isSelected = frame.frame_id === selectedSession.selected_frame_id;
                        const isSubmitting = submittingFrameId === frame.frame_id;
                        return (
                          <div key={frame.frame_id} className={`rounded-lg border p-3 ${isSelected ? "border-primary bg-primary/5" : "border-border"}`}>
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                <div className="flex items-center gap-2">
                                  <p className="text-sm font-medium">{frame.frame_id}</p>
                                  <Badge variant="outline">{frame.narrative_type.replaceAll("_", " ")}</Badge>
                                  {frame.provenance === "synthetic_fallback" ? (
                                    <Badge variant="outline" className="border-amber-500/40 bg-amber-500/10 text-amber-800">
                                      fallback
                                    </Badge>
                                  ) : null}
                                </div>
                                <p className="mt-2 text-sm">{frame.hook}</p>
                                <p className="mt-2 text-xs text-muted-foreground">
                                  Core claim: {frame.core_claim}
                                </p>
                              </div>
                              <Button
                                variant={isSelected ? "default" : "outline"}
                                size="sm"
                                disabled={isSubmitting}
                                onClick={() => handleSelectFrame(selectedSession, frame.frame_id)}
                              >
                                {isSubmitting ? (
                                  <>
                                    <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
                                    {storyFramesWaitingForSelection ? "Continuing" : "Selecting"}
                                  </>
                                ) : isSelected ? (
                                  storyFramesWaitingForSelection ? "Selected" : "Selected"
                                ) : storyFramesWaitingForSelection ? (
                                  "Select & Continue"
                                ) : (
                                  "Use frame"
                                )}
                              </Button>
                            </div>
                          </div>
                        );
                      })
                    )}
                    {storyFramesWaitingForSelection ? (
                      <p className="text-xs text-muted-foreground">
                        Pick one frame to inject the selection into W11 and let the workflow finish the presentation step.
                      </p>
                    ) : null}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-base">
                      <Dna className="h-4 w-4 text-primary" />
                      Claim Map
                      <Badge variant="outline" className="ml-auto border-blue-500/40 bg-blue-500/10 text-blue-700">
                        Guided Support
                      </Badge>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {selectedSession.claim_map.length === 0 ? (
                      <p className="text-sm text-muted-foreground">Link W8, W1, or W6 outputs with RCMXT scores to build the claim map.</p>
                    ) : (
                      selectedSession.claim_map.map((claim, idx) => (
                        <div key={`${claim.claim_text}-${idx}`} className="rounded-lg border p-3">
                          <div className="flex items-start justify-between gap-3">
                            <p className="text-sm font-medium">{claim.claim_text}</p>
                            <Badge className={severityBadgeClass(claim.risk_level)} variant="outline">
                              {claim.risk_level}
                            </Badge>
                          </div>
                          <p className="mt-2 text-xs text-muted-foreground">{claim.rcmxt_summary}</p>
                          {claim.supporting_sources.length > 0 ? (
                            <p className="mt-2 text-xs text-muted-foreground">
                              Sources: {claim.supporting_sources.slice(0, 3).join(", ")}
                            </p>
                          ) : null}
                        </div>
                      ))
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-base">
                      <FileSearch className="h-4 w-4 text-primary" />
                      Reviewer Risks
                      <Badge
                        variant="outline"
                        className={`ml-auto ${maturityBadgeClass(selectedSession.reviewer_risk_report?.maturity ?? "validated_core")}`}
                      >
                        {maturityLabel(selectedSession.reviewer_risk_report?.maturity ?? "validated_core")}
                      </Badge>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="space-y-3 rounded-lg border border-border/70 bg-muted/20 p-3">
                      <div>
                        <p className="text-sm font-medium">Start reviewer risks from a manuscript PDF</p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          Upload a <code>.pdf</code>, <code>.docx</code>, or <code>.doc</code> file directly, or provide a local path under an allowed workflow input root.
                        </p>
                      </div>
                      <input
                        ref={reviewerUploadRef}
                        type="file"
                        accept=".pdf,.doc,.docx"
                        className="hidden"
                        onChange={handleUploadReviewerPaper}
                      />
                      <div className="flex flex-wrap items-center gap-2">
                        <Button
                          className="gap-2"
                          onClick={() => reviewerUploadRef.current?.click()}
                          disabled={uploadingReviewerPaper || !selectedSession}
                        >
                          {uploadingReviewerPaper ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileSearch className="h-4 w-4" />}
                          Upload Paper & Start
                        </Button>
                        {uploadedReviewerFileName ? (
                          <p className="text-xs text-muted-foreground">
                            Last upload: {uploadedReviewerFileName}
                          </p>
                        ) : null}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        Or start from a local path if the paper already exists in an allowed workspace root.
                      </p>
                      <Input
                        value={reviewerPdfPath}
                        onChange={(event) => setReviewerPdfPath(event.target.value)}
                        placeholder="/tmp/manuscript.pdf"
                      />
                      <Button
                        variant="outline"
                        className="gap-2"
                        onClick={handleRunReviewerRisks}
                        disabled={runningReviewerRisks || !reviewerPdfPath.trim()}
                      >
                        {runningReviewerRisks ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileSearch className="h-4 w-4" />}
                        Start Reviewer Risks
                      </Button>
                    </div>
                    {selectedSession.reviewer_risk_report ? (
                      <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-sm font-medium">ReviewerRiskReport v1</p>
                          <Badge
                            variant="outline"
                            className={maturityBadgeClass(selectedSession.reviewer_risk_report.maturity)}
                          >
                            {maturityLabel(selectedSession.reviewer_risk_report.maturity)}
                          </Badge>
                        </div>
                        <p className="mt-2 text-sm text-muted-foreground">
                          {selectedSession.reviewer_risk_report.summary}
                        </p>
                        <p className="mt-2 text-xs text-muted-foreground">
                          {selectedSession.reviewer_risk_report.confidence_or_coverage}
                        </p>
                        {selectedSession.reviewer_risk_report.evidence_provenance.length > 0 ? (
                          <div className="mt-2 space-y-1">
                            {selectedSession.reviewer_risk_report.evidence_provenance.slice(0, 2).map((item) => (
                              <p key={item} className="text-xs text-muted-foreground">
                                {item}
                              </p>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                    {reviewerRisksWaitingForReview ? (
                      <div className="space-y-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
                        <div>
                          <p className="text-sm font-medium">Reviewer checkpoint reached</p>
                          <p className="mt-1 text-sm text-muted-foreground">
                            {reviewerRisksStage?.detail}
                          </p>
                        </div>
                        <Button
                          className="gap-2"
                          onClick={handleResumeReviewerRisks}
                          disabled={resumingReviewerRisks}
                        >
                          {resumingReviewerRisks ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileSearch className="h-4 w-4" />}
                          Resume Reviewer Synthesis
                        </Button>
                      </div>
                    ) : null}
                    {selectedSession.reviewer_risks.length === 0 ? (
                      <p className="text-sm text-muted-foreground">Start or link a W8 reviewer workflow to surface concern-level risks.</p>
                    ) : (
                      selectedSession.reviewer_risks.map((risk, idx) => (
                        <div key={`${risk.title}-${idx}`} className="rounded-lg border p-3">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <p className="text-sm font-medium">{risk.title}</p>
                              <p className="mt-1 text-xs text-muted-foreground">{risk.section}</p>
                            </div>
                            <Badge className={severityBadgeClass(risk.severity)} variant="outline">
                              {risk.severity}
                            </Badge>
                          </div>
                          {risk.detail && risk.detail !== risk.title ? (
                            <p className="mt-2 text-sm text-muted-foreground">{risk.detail}</p>
                          ) : null}
                        </div>
                      ))
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-base">
                      <ShieldCheck className="h-4 w-4 text-primary" />
                      Submission Checks
                      <Badge
                        variant="outline"
                        className={`ml-auto ${maturityBadgeClass(selectedSession.integrity_audit_report?.maturity ?? "validated_core")}`}
                      >
                        {maturityLabel(selectedSession.integrity_audit_report?.maturity ?? "validated_core")}
                      </Badge>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="space-y-3 rounded-lg border border-border/70 bg-muted/20 p-3">
                      <div>
                        <p className="text-sm font-medium">Choose a submission-check mode</p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          Quick draft scan runs directly on session text. Full submission audit launches the full W7 workflow and persists a linked audit run.
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          variant="outline"
                          className="gap-2"
                          onClick={handleRunSubmissionChecks}
                          disabled={runningSubmissionChecks || (!selectedSession.draft_text.trim() && !selectedSession.notes.trim())}
                        >
                          {runningSubmissionChecks ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
                          Quick Draft Scan
                        </Button>
                        <Button
                          className="gap-2"
                          onClick={handleRunFullSubmissionAudit}
                          disabled={runningFullSubmissionAudit || (!selectedSession.query.trim() && !selectedSession.draft_text.trim() && !selectedSession.notes.trim())}
                        >
                          {runningFullSubmissionAudit ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
                          Run Full Submission Audit
                        </Button>
                      </div>
                      {submissionChecksStage ? (
                        <p className="text-xs text-muted-foreground">
                          {submissionChecksStage.detail}
                        </p>
                      ) : null}
                    </div>
                    {selectedSession.integrity_audit_report ? (
                      <div className="rounded-lg border border-border/70 bg-muted/20 p-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-sm font-medium">IntegrityAuditReport v1</p>
                          <Badge
                            variant="outline"
                            className={maturityBadgeClass(selectedSession.integrity_audit_report.maturity)}
                          >
                            {maturityLabel(selectedSession.integrity_audit_report.maturity)}
                          </Badge>
                        </div>
                        <p className="mt-2 text-sm text-muted-foreground">
                          {selectedSession.integrity_audit_report.summary}
                        </p>
                        <p className="mt-2 text-xs text-muted-foreground">
                          {selectedSession.integrity_audit_report.confidence_or_coverage}
                        </p>
                        {selectedSession.integrity_audit_report.evidence_provenance.length > 0 ? (
                          <div className="mt-2 space-y-1">
                            {selectedSession.integrity_audit_report.evidence_provenance.slice(0, 2).map((item) => (
                              <p key={item} className="text-xs text-muted-foreground">
                                {item}
                              </p>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                    {selectedSession.integrity_flags.length === 0 ? (
                      <p className="text-sm text-muted-foreground">Run a quick draft scan or a full W7 audit to bring submission blockers into the manuscript session.</p>
                    ) : (
                      selectedSession.integrity_flags.map((flag, idx) => (
                        <div key={`${flag.title}-${idx}`} className="rounded-lg border p-3">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <p className="text-sm font-medium">{flag.title}</p>
                              <div className="mt-1 flex flex-wrap items-center gap-2">
                                <p className="text-xs text-muted-foreground">{flag.category}</p>
                                <Badge variant="outline" className="text-[10px]">
                                  {flag.generated_by.startsWith("manuscript_session:quick_check") ? "quick scan" : flag.generated_by.startsWith("W7:") ? "full audit" : "linked"}
                                </Badge>
                              </div>
                            </div>
                            <Badge className={severityBadgeClass(flag.severity)} variant="outline">
                              {flag.severity}
                            </Badge>
                          </div>
                          {flag.detail ? <p className="mt-2 text-sm text-muted-foreground">{flag.detail}</p> : null}
                          {flag.suggestion ? <p className="mt-2 text-xs text-muted-foreground">Suggestion: {flag.suggestion}</p> : null}
                        </div>
                      ))
                    )}
                  </CardContent>
                </Card>
              </div>

              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">Derived Outline</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {selectedSession.outline.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      The outline appears after you select a story frame and link enough evidence or defense outputs.
                    </p>
                  ) : (
                    selectedSession.outline.map((section, idx) => (
                      <div key={`${section.title}-${idx}`} className="rounded-lg border p-4">
                        <p className="text-sm font-medium">{section.title}</p>
                        <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
                          {section.bullets.map((bullet, bulletIdx) => (
                            <li key={`${section.title}-${bulletIdx}`}>- {bullet}</li>
                          ))}
                        </ul>
                      </div>
                    ))
                  )}
                </CardContent>
              </Card>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
