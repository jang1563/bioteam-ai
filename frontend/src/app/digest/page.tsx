"use client";

import React, { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
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
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import {
  Plus,
  Play,
  ExternalLink,
  Newspaper,
  Loader2,
  Trash2,
  BookOpen,
  TrendingUp,
  Star,
  AlertCircle,
  X,
  Clock,
  Activity,
  SkipForward,
} from "lucide-react";
import { TableSkeleton } from "@/components/dashboard/loading-skeletons";
import {
  useTopics,
  useDigestEntries,
  useDigestReports,
  useRunDigest,
  useDigestStats,
  useSchedulerStatus,
} from "@/hooks/use-digest";
import type {
  CreateTopicRequest,
  DigestEntry,
  DigestReport,
  DigestSource,
  SchedulerStatus,
  TopicProfile,
  TopicScheduleInfo,
} from "@/types/api";

const SOURCE_LABELS: Record<string, string> = {
  pubmed: "PubMed",
  biorxiv: "bioRxiv",
  arxiv: "arXiv",
  github: "GitHub",
  huggingface: "HuggingFace",
  semantic_scholar: "Semantic Scholar",
};

const SOURCE_COLORS: Record<string, string> = {
  pubmed: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  biorxiv: "bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200",
  arxiv: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  github: "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200",
  huggingface: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
  semantic_scholar: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200",
};

export default function DigestPage() {
  const { topics, loading: topicsLoading, error: topicsError, create, remove } = useTopics();
  const [selectedTopicId, setSelectedTopicId] = useState<string | undefined>();
  const [sourceFilter, setSourceFilter] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<"relevance" | "date">("relevance");
  const [runError, setRunError] = useState<string | null>(null);

  const selectedTopic = topics.find((t) => t.id === selectedTopicId) ?? topics[0];
  const topicId = selectedTopic?.id;

  const { entries, loading: entriesLoading, error: entriesError, refresh: refreshEntries } = useDigestEntries(
    topicId,
    sourceFilter === "all" ? undefined : (sourceFilter as DigestSource),
    7,
    sortBy,
  );
  const { reports, loading: reportsLoading, error: reportsError, refresh: refreshReports } = useDigestReports(topicId);
  const { run, running, error: runHookError } = useRunDigest();
  const { stats } = useDigestStats();
  const { status: schedulerStatus } = useSchedulerStatus();

  const handleRunAll = async () => {
    const activeTopics = topics.filter((t) => t.is_active);
    for (const t of activeTopics) {
      try { await run(t.id); } catch { /* continue */ }
    }
    refreshEntries();
    refreshReports();
  };

  const filteredEntries = search
    ? entries.filter(
        (e) =>
          e.title.toLowerCase().includes(search.toLowerCase()) ||
          e.abstract.toLowerCase().includes(search.toLowerCase()),
      )
    : entries;

  const latestReport = reports[0];

  const handleRun = async () => {
    if (!topicId) return;
    setRunError(null);
    try {
      await run(topicId);
      refreshEntries();
      refreshReports();
    } catch (e) {
      setRunError(e instanceof Error ? e.message : "Failed to run digest");
    }
  };

  const activeError = runError || runHookError || topicsError || entriesError || reportsError;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Newspaper className="h-6 w-6 text-primary" aria-hidden="true" />
          <h1 className="text-2xl font-bold tracking-tight">Research Digest</h1>
        </div>
        <div className="flex items-center gap-2">
          {topicId && (
            <Button size="sm" onClick={handleRun} disabled={running}>
              {running ? (
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
              ) : (
                <Play className="mr-1 h-4 w-4" />
              )}
              {running ? "Fetching..." : "Run Now"}
            </Button>
          )}
          <CreateTopicDialog onCreate={create} />
        </div>
      </div>

      {/* Scheduler Status Card */}
      {schedulerStatus && (
        <SchedulerStatusCard
          status={schedulerStatus}
          onRunAll={handleRunAll}
          running={running}
        />
      )}

      {/* Error Banner */}
      {activeError && (
        <div className="flex items-center gap-2 rounded-md border border-destructive/50 bg-destructive/10 px-4 py-2 text-sm text-destructive" role="alert">
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span className="flex-1">{activeError}</span>
          <button
            onClick={() => setRunError(null)}
            className="shrink-0 rounded p-0.5 hover:bg-destructive/20"
            aria-label="Dismiss error"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* Topic Selector + Stats */}
      <div className="flex flex-wrap items-center gap-3">
        <label htmlFor="topic-select" className="sr-only">Select topic</label>
        <Select
          value={topicId ?? ""}
          onValueChange={setSelectedTopicId}
        >
          <SelectTrigger className="w-[240px]" id="topic-select" aria-label="Select topic">
            <SelectValue placeholder="Select a topic..." />
          </SelectTrigger>
          <SelectContent>
            {topics.map((t) => (
              <SelectItem key={t.id} value={t.id}>
                {t.name} ({t.schedule})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {stats && (
          <div className="flex gap-4 text-xs text-muted-foreground">
            <span>{stats.total_topics} topics</span>
            <span>{stats.total_entries} entries</span>
            <span>{stats.total_reports} reports</span>
          </div>
        )}
      </div>

      {topicsLoading ? (
        <TableSkeleton rows={3} />
      ) : topics.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            No topic profiles yet. Create one to start monitoring research.
          </CardContent>
        </Card>
      ) : (
        <Tabs defaultValue="entries" className="space-y-4">
          <TabsList>
            <TabsTrigger value="entries">
              <BookOpen className="mr-1.5 h-3.5 w-3.5" />
              Entries ({filteredEntries.length})
            </TabsTrigger>
            <TabsTrigger value="report">
              <TrendingUp className="mr-1.5 h-3.5 w-3.5" />
              Latest Report
            </TabsTrigger>
            <TabsTrigger value="topics">
              <Star className="mr-1.5 h-3.5 w-3.5" />
              Topics
            </TabsTrigger>
          </TabsList>

          {/* Entries Tab */}
          <TabsContent value="entries" className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              <div className="relative flex-1 max-w-xs">
                <Input
                  placeholder="Search papers..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  aria-label="Search papers"
                />
              </div>
              <label htmlFor="source-filter" className="sr-only">Filter by source</label>
              <Select value={sourceFilter} onValueChange={setSourceFilter}>
                <SelectTrigger className="w-[160px]" id="source-filter" aria-label="Filter by source">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Sources</SelectItem>
                  <SelectItem value="pubmed">PubMed</SelectItem>
                  <SelectItem value="biorxiv">bioRxiv</SelectItem>
                  <SelectItem value="arxiv">arXiv</SelectItem>
                  <SelectItem value="github">GitHub</SelectItem>
                  <SelectItem value="huggingface">HuggingFace</SelectItem>
                  <SelectItem value="semantic_scholar">Semantic Scholar</SelectItem>
                </SelectContent>
              </Select>
              <label htmlFor="sort-by" className="sr-only">Sort by</label>
              <Select value={sortBy} onValueChange={(v) => setSortBy(v as "relevance" | "date")}>
                <SelectTrigger className="w-[140px]" id="sort-by" aria-label="Sort by">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="relevance">By Relevance</SelectItem>
                  <SelectItem value="date">By Date</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {entriesLoading ? (
              <TableSkeleton rows={5} />
            ) : filteredEntries.length === 0 ? (
              <Card>
                <CardContent className="py-12 text-center text-sm text-muted-foreground">
                  No entries found. Run a digest to fetch papers.
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-2">
                {filteredEntries.map((entry) => (
                  <EntryCard key={entry.id} entry={entry} />
                ))}
              </div>
            )}
          </TabsContent>

          {/* Report Tab */}
          <TabsContent value="report" className="space-y-4">
            {reportsLoading ? (
              <TableSkeleton rows={3} />
            ) : latestReport ? (
              <ReportCard report={latestReport} />
            ) : (
              <Card>
                <CardContent className="py-12 text-center text-sm text-muted-foreground">
                  No reports yet. Run a digest to generate one.
                </CardContent>
              </Card>
            )}
          </TabsContent>

          {/* Topics Tab */}
          <TabsContent value="topics" className="space-y-4">
            <div className="grid gap-3 md:grid-cols-2">
              {topics.map((topic) => (
                <TopicCard key={topic.id} topic={topic} onDelete={remove} />
              ))}
            </div>
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}

function EntryCard({ entry }: { entry: DigestEntry }) {
  const [showAbstract, setShowAbstract] = useState(false);

  return (
    <>
      <Card className="hover:border-primary/30 transition-colors">
        <CardContent className="p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0 space-y-1">
              <div className="flex items-center gap-2">
                <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${SOURCE_COLORS[entry.source] ?? "bg-gray-100 text-gray-800"}`}>
                  {SOURCE_LABELS[entry.source] ?? entry.source}
                </span>
                <span className="font-mono text-[10px] text-muted-foreground">
                  {(entry.relevance_score * 100).toFixed(0)}% match
                </span>
                {entry.published_at && (
                  <span className="text-[10px] text-muted-foreground">
                    {entry.published_at}
                  </span>
                )}
              </div>
              <h3 className="text-sm font-medium leading-snug">{entry.title}</h3>
              {entry.authors.length > 0 && (
                <p className="text-xs text-muted-foreground">
                  {entry.authors.slice(0, 3).join(", ")}
                  {entry.authors.length > 3 && ` +${entry.authors.length - 3}`}
                </p>
              )}
              {entry.abstract && (
                <div>
                  <p className="text-xs text-muted-foreground line-clamp-2">
                    {entry.abstract}
                  </p>
                  {entry.abstract.length > 150 && (
                    <button
                      onClick={() => setShowAbstract(true)}
                      className="text-[10px] text-primary hover:underline mt-0.5"
                    >
                      Show full abstract
                    </button>
                  )}
                </div>
              )}
            </div>
            {entry.url && (
              <a
                href={entry.url}
                target="_blank"
                rel="noopener noreferrer"
                className="shrink-0"
                aria-label={`Open ${entry.title}`}
              >
                <ExternalLink className="h-4 w-4 text-muted-foreground hover:text-primary" />
              </a>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Abstract expand dialog */}
      <Dialog open={showAbstract} onOpenChange={setShowAbstract}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-sm leading-snug">{entry.title}</DialogTitle>
            <DialogDescription className="text-xs">
              {entry.authors.slice(0, 5).join(", ")}
              {entry.authors.length > 5 && ` +${entry.authors.length - 5}`}
              {entry.published_at && ` | ${entry.published_at}`}
            </DialogDescription>
          </DialogHeader>
          <p className="text-sm leading-relaxed whitespace-pre-wrap">{entry.abstract}</p>
          {entry.url && (
            <a
              href={entry.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
            >
              <ExternalLink className="h-3 w-3" />
              View paper
            </a>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

function ReportCard({ report }: { report: DigestReport }) {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Digest Summary
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            {report.entry_count} entries | Cost: ${report.cost.toFixed(4)} |{" "}
            {new Date(report.created_at).toLocaleDateString()}
          </p>
        </CardHeader>
        <CardContent>
          {report.summary ? (
            <p className="text-sm leading-relaxed">{report.summary}</p>
          ) : (
            <p className="text-sm text-muted-foreground">No LLM summary available.</p>
          )}
        </CardContent>
      </Card>

      {/* Source breakdown */}
      {Object.keys(report.source_breakdown).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Sources</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {Object.entries(report.source_breakdown).map(([src, count]) => (
                <Badge key={src} variant="outline" className="text-xs">
                  {SOURCE_LABELS[src] ?? src}: {count}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Highlights */}
      {report.highlights.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Highlights</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {report.highlights.map((hl, i) => (
                <li key={i} className="text-sm">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{hl.title}</span>
                    {hl.source && (
                      <Badge variant="outline" className="text-[10px]">
                        {SOURCE_LABELS[hl.source] ?? hl.source}
                      </Badge>
                    )}
                    {hl.url && (
                      <a
                        href={hl.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        aria-label={`Open ${hl.title}`}
                      >
                        <ExternalLink className="h-3 w-3 text-muted-foreground hover:text-primary" />
                      </a>
                    )}
                  </div>
                  {hl.one_liner && (
                    <p className="text-xs text-muted-foreground mt-0.5">{hl.one_liner}</p>
                  )}
                  {hl.why_important && (
                    <p className="text-[10px] text-muted-foreground/70 mt-0.5 italic">{hl.why_important}</p>
                  )}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function TopicCard({
  topic,
  onDelete,
}: {
  topic: TopicProfile;
  onDelete: (id: string) => Promise<void>;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">{topic.name}</CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant={topic.is_active ? "default" : "secondary"} className="text-[10px]">
              {topic.schedule}
            </Badge>
            <Button
              size="icon"
              variant="ghost"
              className="h-6 w-6"
              aria-label={`Delete topic: ${topic.name}`}
              onClick={() => {
                if (window.confirm(`Delete topic "${topic.name}"?`)) {
                  onDelete(topic.id);
                }
              }}
            >
              <Trash2 className="h-3 w-3 text-destructive" aria-hidden="true" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        <div>
          <p className="text-[10px] font-medium text-muted-foreground uppercase">Queries</p>
          <div className="flex flex-wrap gap-1 mt-1">
            {topic.queries.map((q, i) => (
              <Badge key={i} variant="outline" className="text-[10px]">{q}</Badge>
            ))}
          </div>
        </div>
        <div>
          <p className="text-[10px] font-medium text-muted-foreground uppercase">Sources</p>
          <div className="flex flex-wrap gap-1 mt-1">
            {topic.sources.map((s) => (
              <span
                key={s}
                className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${SOURCE_COLORS[s] ?? "bg-gray-100 text-gray-800"}`}
              >
                {SOURCE_LABELS[s] ?? s}
              </span>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function CreateTopicDialog({
  onCreate,
}: {
  onCreate: (req: CreateTopicRequest) => Promise<TopicProfile>;
}) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    name: "",
    queries: "",
    schedule: "daily" as "daily" | "weekly" | "manual",
  });
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    if (!form.name.trim() || !form.queries.trim()) return;
    setLoading(true);
    try {
      await onCreate({
        name: form.name.trim(),
        queries: form.queries.split("\n").map((q) => q.trim()).filter(Boolean),
        schedule: form.schedule,
      });
      setOpen(false);
      setForm({ name: "", queries: "", schedule: "daily" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline">
          <Plus className="mr-1 h-4 w-4" /> New Topic
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create Topic Profile</DialogTitle>
          <DialogDescription>
            Define a research topic to monitor across multiple sources.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 pt-2">
          <Field label="Topic Name" htmlFor="topic-name">
            <Input
              id="topic-name"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="e.g., AI in Biology"
            />
          </Field>
          <Field label="Search Queries (one per line)" htmlFor="topic-queries">
            <textarea
              id="topic-queries"
              className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              value={form.queries}
              onChange={(e) => setForm((f) => ({ ...f, queries: e.target.value }))}
              placeholder={"AI biology research\nmachine learning genomics\nfoundation models biology"}
            />
          </Field>
          <Field label="Schedule" htmlFor="topic-schedule">
            <Select
              value={form.schedule}
              onValueChange={(v) => setForm((f) => ({ ...f, schedule: v as typeof f.schedule }))}
            >
              <SelectTrigger id="topic-schedule"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="daily">Daily</SelectItem>
                <SelectItem value="weekly">Weekly</SelectItem>
                <SelectItem value="manual">Manual Only</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Button
            onClick={handleSubmit}
            disabled={loading || !form.name.trim() || !form.queries.trim()}
            className="w-full"
          >
            {loading ? "Creating..." : "Create Topic"}
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

// ── Scheduler Status Card ──────────────────────────────────────────────────────

function formatMinutes(minutes: number | null): string {
  if (minutes === null) return "—";
  if (minutes === 0) return "Overdue";
  if (minutes < 60) return `${minutes}m`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

function formatLastRun(iso: string | null): string {
  if (!iso) return "Never";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 2) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const h = Math.floor(mins / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function SchedulerStatusCard({
  status,
  onRunAll,
  running,
}: {
  status: SchedulerStatus;
  onRunAll: () => void;
  running: boolean;
}) {
  const activeTopics = status.topics.filter((t) => t.is_active);
  const overdueCount = status.topics.filter((t) => t.overdue).length;

  return (
    <Card className="border-muted/60">
      <CardContent className="p-4">
        {/* Header row */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            <span className="text-sm font-medium">Scheduler</span>
            <Badge
              variant={status.running ? "default" : "secondary"}
              className="text-[10px] h-4 px-1.5"
            >
              {status.running ? "Running" : "Stopped"}
            </Badge>
            {overdueCount > 0 && (
              <Badge variant="destructive" className="text-[10px] h-4 px-1.5">
                {overdueCount} overdue
              </Badge>
            )}
            <span className="text-[10px] text-muted-foreground">
              checks every {status.check_interval_minutes}m
            </span>
          </div>
          {activeTopics.length > 0 && (
            <Button
              size="sm"
              variant="outline"
              className="h-6 text-xs px-2"
              onClick={onRunAll}
              disabled={running}
            >
              {running ? (
                <Loader2 className="mr-1 h-3 w-3 animate-spin" />
              ) : (
                <SkipForward className="mr-1 h-3 w-3" />
              )}
              Run All
            </Button>
          )}
        </div>

        {/* Per-topic rows */}
        {status.topics.length === 0 ? (
          <p className="text-xs text-muted-foreground">No topics configured.</p>
        ) : (
          <div className="divide-y divide-border/40">
            {status.topics.map((t) => (
              <TopicScheduleRow key={t.topic_id} topic={t} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function TopicScheduleRow({ topic }: { topic: TopicScheduleInfo }) {
  const isManual = topic.schedule === "manual";

  return (
    <div className="flex items-center gap-3 py-1.5 text-xs">
      {/* Active indicator */}
      <span
        className={`h-1.5 w-1.5 rounded-full shrink-0 ${topic.is_active ? "bg-green-500" : "bg-muted"}`}
        aria-label={topic.is_active ? "active" : "inactive"}
      />

      {/* Name */}
      <span className="flex-1 font-medium truncate">{topic.name}</span>

      {/* Schedule badge */}
      <Badge
        variant="outline"
        className={`text-[10px] h-4 px-1.5 shrink-0 ${isManual ? "text-muted-foreground" : ""}`}
      >
        {topic.schedule}
      </Badge>

      {/* Last run */}
      <span className="text-muted-foreground shrink-0 w-16 text-right">
        {formatLastRun(topic.last_run_at)}
      </span>

      {/* Next run */}
      <span
        className={`flex items-center gap-1 shrink-0 w-20 text-right ${
          topic.overdue
            ? "text-destructive font-medium"
            : isManual
            ? "text-muted-foreground"
            : "text-foreground"
        }`}
      >
        {!isManual && <Clock className="h-3 w-3 shrink-0" aria-hidden="true" />}
        {isManual ? "manual" : formatMinutes(topic.minutes_until_next)}
      </span>
    </div>
  );
}
