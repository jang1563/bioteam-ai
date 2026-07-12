"use client";

import Link from "next/link";
import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AgentGrid } from "@/components/dashboard/agent-grid";
import { WorkflowCard } from "@/components/dashboard/workflow-card";
import { ActivityFeed } from "@/components/dashboard/activity-feed";
import { AgentDetailSheet } from "@/components/dashboard/agent-detail-sheet";
import { WorkflowDetailSheet } from "@/components/dashboard/workflow-detail-sheet";
import { CreateWorkflowDialog } from "@/components/dashboard/create-workflow-dialog";
import {
  AgentGridSkeleton,
  WorkflowListSkeleton,
  ActivityFeedSkeleton,
} from "@/components/dashboard/loading-skeletons";
import { ManuscriptStudioWorkspace } from "@/components/manuscript/manuscript-studio-workspace";
import { useAgents } from "@/hooks/use-agents";
import { useWorkflows } from "@/hooks/use-workflows";
import { useSSE } from "@/hooks/use-sse";
import { useAppStore } from "@/stores/app-store";
import { api } from "@/lib/api-client";
import type { ColdStartStatus, ColdStartResponse } from "@/types/api";
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  Database,
  Dna,
  FileSearch,
  FileText,
  LayoutDashboard,
  Loader2,
  Rocket,
  ShieldCheck,
} from "lucide-react";

const studioSteps = [
  {
    title: "Input bundle",
    description: "Start from a draft, notes, or a few key papers instead of a blank page.",
  },
  {
    title: "Story frame",
    description: "Choose the strongest narrative angle before you commit to prose.",
  },
  {
    title: "Claim map",
    description: "See which claims are strong, weak, or overstated before review.",
  },
  {
    title: "Defense checks",
    description: "Inspect reviewer risks and submission blockers before you ship the manuscript.",
  },
];

const outputCards = [
  {
    title: "Best Story Frame",
    description:
      "Compare mechanism discovery, paradigm challenge, clinical implication, and negative reframe angles before drafting.",
    icon: BookOpen,
  },
  {
    title: "Claim Strength Map",
    description:
      "Score major claims with RCMXT so you know which statements need stronger support or softer wording.",
    icon: Dna,
  },
  {
    title: "Reviewer Attack Surface",
    description:
      "Preview the kinds of concerns real reviewers are likely to raise, grounded in open peer review patterns.",
    icon: FileSearch,
  },
  {
    title: "Submission Checks",
    description:
      "Catch integrity issues such as naming, statistical, citation, and accession problems before submission.",
    icon: ShieldCheck,
  },
];

const studioSurfaces = [
  {
    title: "Story Frames",
    href: "/story-planning",
    description: "Generate and rank narrative frames before you start writing.",
    icon: BookOpen,
  },
  {
    title: "Claim Strength",
    href: "/rcmxt",
    description: "Inspect RCMXT evidence scores for the claims you want to make.",
    icon: Dna,
  },
  {
    title: "Reviewer Risks",
    href: "/peer-review",
    description: "See where methodology, novelty, and citation concerns are likely to land.",
    icon: FileSearch,
  },
  {
    title: "Submission Checks",
    href: "/integrity",
    description: "Run biology-specific integrity checks before the manuscript leaves your desk.",
    icon: ShieldCheck,
  },
];

const capabilityTiers = [
  {
    title: "Validated Core",
    badgeClass: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700",
    detail: "Lead with benchmark-backed reviewer risks and submission checks when presenting the project.",
    items: ["Reviewer Risks", "Submission Checks"],
  },
  {
    title: "Guided Support",
    badgeClass: "border-blue-500/40 bg-blue-500/10 text-blue-700",
    detail: "Story framing and claim calibration help make the manuscript stronger, but they support the core proof story.",
    items: ["Story Frames", "Claim Strength"],
  },
  {
    title: "Research Preview",
    badgeClass: "border-slate-400/40 bg-slate-400/10 text-slate-700",
    detail: "Broader surfaces remain valuable long-term, but they should not crowd out the manuscript-defense wedge.",
    items: ["Extended workflows", "Broader dashboard"],
  },
] as const;

function ColdStartBanner() {
  const [status, setStatus] = useState<ColdStartStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [quickStarting, setQuickStarting] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const data = await api.get<ColdStartStatus>("/api/v1/cold-start/status");
      setStatus(data);
    } catch {
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  const handleQuickStart = async () => {
    setQuickStarting(true);
    try {
      await api.post<ColdStartResponse>("/api/v1/cold-start/quick");
      await fetchStatus();
    } catch {
      // Backend might not be running yet.
    } finally {
      setQuickStarting(false);
    }
  };

  if (loading || dismissed || !status) return null;

  if (status.is_initialized && status.critical_agents_healthy && status.has_literature) {
    return null;
  }

  const issues: string[] = [];
  if (!status.is_initialized) issues.push("System not initialized");
  if (!status.critical_agents_healthy) issues.push("Some critical agents unhealthy");
  if (!status.has_literature) issues.push("No literature seeded");
  if (!status.has_lab_kb) issues.push("No Lab KB entries");

  const severity = !status.is_initialized || !status.critical_agents_healthy ? "error" : "warning";

  return (
    <Card className={severity === "error" ? "border-destructive" : "border-yellow-500/50"}>
      <CardContent className="py-3">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <AlertTriangle
              className={`mt-0.5 h-4 w-4 shrink-0 ${severity === "error" ? "text-destructive" : "text-yellow-500"}`}
            />
            <div className="space-y-1">
              <p className="text-sm font-medium">
                {!status.is_initialized ? "Cold Start Required" : "Setup Incomplete"}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {issues.map((issue) => (
                  <Badge key={issue} variant="outline" className="text-xs">
                    {issue}
                  </Badge>
                ))}
              </div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Database className="h-3 w-3" />
                {status.total_documents} documents | {status.agents_registered} agents
              </div>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button size="sm" variant="outline" onClick={handleQuickStart} disabled={quickStarting}>
              {quickStarting ? (
                <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />
              ) : (
                <Rocket className="mr-1.5 h-3 w-3" />
              )}
              Quick Start
            </Button>
            <Button size="sm" variant="ghost" className="text-xs" onClick={() => setDismissed(true)}>
              Dismiss
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function ManuscriptStudioPage() {
  const { agents, loading: agentsLoading } = useAgents();
  const { workflows, loading: workflowsLoading, refresh: refreshWorkflows } = useWorkflows();
  const events = useAppStore((s) => s.events);
  const addEvent = useAppStore((s) => s.addEvent);

  useSSE((event) => {
    addEvent(event);
    if (event.event_type.startsWith("workflow.")) {
      refreshWorkflows();
    }
  });

  return (
    <div className="space-y-8">
      <section className="overflow-hidden rounded-2xl border border-border bg-gradient-to-br from-primary/10 via-background to-background">
        <div className="space-y-6 p-6 lg:p-8">
          <div className="space-y-3">
            <Badge variant="outline" className="gap-1 border-primary/40 bg-primary/5 text-primary">
              <FileText className="h-3 w-3" />
              Defensible manuscript copilot for biology
            </Badge>
            <div className="space-y-3">
              <h1 className="max-w-3xl text-3xl font-bold tracking-tight lg:text-4xl">
                Manuscript Studio
              </h1>
              <p className="max-w-3xl text-base text-muted-foreground lg:text-lg">
                Turn biology notes, drafts, and key papers into a manuscript you can defend. Choose the
                strongest story, score claim strength, predict reviewer attacks, and catch integrity issues
                before submission.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Link href="/story-planning">
              <Button className="gap-2">
                Open Story Frames
                <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
            <Link href="/peer-review">
              <Button variant="outline" className="gap-2">
                Review Risks
                <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
            <CreateWorkflowDialog onCreated={refreshWorkflows} />
          </div>

          <div className="grid gap-3 lg:grid-cols-4">
            {studioSteps.map((step, idx) => (
              <Card key={step.title} className="border-border/70 bg-background/70">
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2 text-sm">
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                      {idx + 1}
                    </span>
                    {step.title}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">{step.description}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      <ManuscriptStudioWorkspace workflows={workflows} />

      <section className="space-y-4">
        <div>
          <h2 className="text-sm font-medium uppercase tracking-wide text-muted-foreground">
            What you get
          </h2>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
            BioTeam-AI is not just a writing assistant. It helps you make better framing decisions, calibrate
            claims, anticipate reviewer concerns, and fix submission blockers before they become expensive.
          </p>
        </div>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {outputCards.map(({ title, description, icon: Icon }) => (
            <Card key={title}>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Icon className="h-4 w-4 text-primary" />
                  {title}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">{description}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <section className="space-y-4">
        <div>
          <h2 className="text-sm font-medium uppercase tracking-wide text-muted-foreground">
            Capability Maturity
          </h2>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
            The strongest external story is narrow on purpose: validated reviewer-risk and submission-check
            workflows up front, with framing and evidence support layered beneath them.
          </p>
        </div>
        <div className="grid gap-4 xl:grid-cols-3">
          {capabilityTiers.map((tier) => (
            <Card key={tier.title}>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center justify-between gap-3 text-base">
                  {tier.title}
                  <Badge variant="outline" className={tier.badgeClass}>
                    {tier.title}
                  </Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm text-muted-foreground">{tier.detail}</p>
                <div className="flex flex-wrap gap-2">
                  {tier.items.map((item) => (
                    <Badge key={item} variant="outline" className="text-[10px]">
                      {item}
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <ColdStartBanner />

      <section className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold tracking-tight">Studio Surfaces</h2>
            <p className="text-sm text-muted-foreground">
              Open the core tools that make a manuscript stronger before it reaches peer review.
            </p>
          </div>
        </div>
        <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
          {studioSurfaces.map(({ title, href, description, icon: Icon }) => (
            <Card key={title} className="transition-colors hover:border-primary/40">
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Icon className="h-4 w-4 text-primary" />
                  {title}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-sm text-muted-foreground">{description}</p>
                <Link href={href}>
                  <Button variant="outline" size="sm" className="gap-2">
                    Open
                    <ArrowRight className="h-3.5 w-3.5" />
                  </Button>
                </Link>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <section className="space-y-4">
        <div className="flex items-center gap-2">
          <LayoutDashboard className="h-5 w-5 text-muted-foreground" />
          <div>
            <h2 className="text-lg font-semibold tracking-tight">Ops Console</h2>
            <p className="text-sm text-muted-foreground">
              Workflow and agent visibility stay available here, but the product starts from manuscript
              defense rather than system administration.
            </p>
          </div>
        </div>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">
              Agents {!agentsLoading && `(${agents.length})`}
            </CardTitle>
          </CardHeader>
          <CardContent>{agentsLoading ? <AgentGridSkeleton /> : <AgentGrid agents={agents} />}</CardContent>
        </Card>

        <div className="grid gap-6 lg:grid-cols-3">
          <div className="space-y-3 lg:col-span-2">
            <h2 className="text-sm font-medium text-muted-foreground">
              Live Workflows {!workflowsLoading && `(${workflows.length})`}
            </h2>
            {workflowsLoading ? (
              <WorkflowListSkeleton />
            ) : workflows.length === 0 ? (
              <Card className="border-dashed">
                <CardContent className="py-8 text-center text-sm text-muted-foreground">
                  No workflows yet. Start with Story Frames, Reviewer Risks, or launch a workflow from the
                  studio.
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

          <div>
            <h2 className="mb-3 text-sm font-medium text-muted-foreground">Activity Feed</h2>
            <Card>
              <CardContent className="p-3">
                {events.length === 0 && agentsLoading ? (
                  <ActivityFeedSkeleton />
                ) : (
                  <ActivityFeed events={events} />
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      <AgentDetailSheet />
      <WorkflowDetailSheet />
    </div>
  );
}
