"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Send,
  Loader2,
  Brain,
  Workflow,
  Clock,
  DollarSign,
  BookOpen,
  Radio,
  User,
  Plus,
  MessageSquare,
  Trash2,
  Pencil,
  Check,
  X,
  Copy,
  AlertTriangle,
  ExternalLink,
} from "lucide-react";
import { useDirectQueryStream } from "@/hooks/use-direct-query-stream";
import { useConversations } from "@/hooks/use-conversations";
import type { ConversationTurn } from "@/types/api";

const STATUS_LABELS: Record<string, string> = {
  classifying: "Classifying query...",
  retrieving: "Retrieving knowledge context...",
  streaming: "Generating answer...",
  done: "Complete",
  error: "Error",
};

export default function QueryPage() {
  const [query, setQuery] = useState("");
  const stream = useDirectQueryStream();
  const convs = useConversations();
  const scrollBottomRef = useRef<HTMLDivElement>(null);

  // Active conversation state
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [activeTurns, setActiveTurns] = useState<ConversationTurn[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");

  const isActive = stream.status !== "idle" && stream.status !== "done" && stream.status !== "error";

  // Auto-scroll to bottom when turns update or streaming
  useEffect(() => {
    scrollBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeTurns.length, isActive]);

  // Load conversations on mount
  useEffect(() => {
    convs.refresh();
  }, [convs]);

  const handleSubmit = () => {
    if (!query.trim() || isActive) return;
    const submittedQuery = query.trim();
    void stream.execute(submittedQuery, activeConvId, {
      onDone: (data) => {
        const newConvId = data.conversation_id;
        if (newConvId) {
          setActiveConvId(() => newConvId);
          setActiveTurns((prev) => {
            const newTurn: ConversationTurn = {
              id: crypto.randomUUID(),
              turn_number: prev.length + 1,
              query: submittedQuery,
              classification_type: data.classification_type ?? "simple_query",
              routed_agent: data.routed_agent ?? null,
              answer: data.answer ?? (stream.streamedText || null),
              sources: data.sources ?? [],
              ungrounded_citations: data.ungrounded_citations ?? [],
              cost: data.total_cost ?? 0,
              duration_ms: data.duration_ms ?? 0,
              created_at: new Date().toISOString(),
            };
            return [...prev, newTurn];
          });
          void convs.refresh();
        }
        setQuery("");
      },
    });
  };

  const handleNewConversation = () => {
    stream.reset();
    setActiveConvId(null);
    setActiveTurns([]);
    setQuery("");
  };

  const handleSelectConversation = async (id: string) => {
    if (id === activeConvId) return;
    stream.reset();
    setQuery("");
    try {
      const detail = await convs.loadConversation(id);
      setActiveConvId(detail.id);
      setActiveTurns(detail.turns);
    } catch {
      // Conversation may have been deleted
      convs.refresh();
    }
  };

  const handleDelete = async (id: string) => {
    await convs.deleteConversation(id);
    if (activeConvId === id) {
      handleNewConversation();
    }
  };

  const handleRename = async (id: string) => {
    if (!editTitle.trim()) {
      setEditingId(null);
      return;
    }
    await convs.renameConversation(id, editTitle.trim());
    setEditingId(null);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="flex gap-6 h-[calc(100vh-8rem)]">
      {/* Conversation Sidebar */}
      <div className="w-64 shrink-0 flex flex-col">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-medium text-muted-foreground">Conversations</h2>
          <Button variant="ghost" size="sm" onClick={handleNewConversation} title="New conversation">
            <Plus className="h-4 w-4" />
          </Button>
        </div>
        <ScrollArea className="flex-1 -mx-1">
          <div className="space-y-1 px-1">
            {convs.conversations.length === 0 && !convs.loading && (
              <p className="text-xs text-muted-foreground py-4 text-center">No conversations yet</p>
            )}
            {convs.conversations.map((c) => (
              <div
                key={c.id}
                className={`group flex items-center gap-1 rounded-md px-2 py-1.5 text-sm cursor-pointer transition-colors ${
                  activeConvId === c.id
                    ? "bg-accent text-accent-foreground"
                    : "hover:bg-accent/50"
                }`}
              >
                {editingId === c.id ? (
                  <div className="flex items-center gap-1 flex-1 min-w-0">
                    <Input
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") handleRename(c.id);
                        if (e.key === "Escape") setEditingId(null);
                      }}
                      className="h-6 text-xs"
                      autoFocus
                    />
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-5 w-5 p-0"
                      onClick={() => handleRename(c.id)}
                    >
                      <Check className="h-3 w-3" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-5 w-5 p-0"
                      onClick={() => setEditingId(null)}
                    >
                      <X className="h-3 w-3" />
                    </Button>
                  </div>
                ) : (
                  <>
                    <div
                      className="flex items-center gap-2 flex-1 min-w-0"
                      onClick={() => handleSelectConversation(c.id)}
                    >
                      <MessageSquare className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      <span className="truncate text-xs">{c.title || "Untitled"}</span>
                    </div>
                    <div className="hidden group-hover:flex items-center gap-0.5 shrink-0">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-5 w-5 p-0"
                        onClick={(e) => {
                          e.stopPropagation();
                          setEditingId(c.id);
                          setEditTitle(c.title);
                        }}
                      >
                        <Pencil className="h-3 w-3" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-5 w-5 p-0 text-destructive"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDelete(c.id);
                        }}
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        </ScrollArea>
        {convs.conversations.length > 0 && (
          <div className="pt-2 border-t mt-2">
            <p className="text-xs text-muted-foreground text-center">
              {convs.conversations.length} conversation{convs.conversations.length !== 1 ? "s" : ""}
            </p>
          </div>
        )}
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <div className="mb-4">
          <h1 className="text-2xl font-bold tracking-tight">Direct Query</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Ask a research question. The Research Director classifies and routes it to the appropriate specialist agent.
          </p>
        </div>

        {/* Chat-like conversation history */}
        <ScrollArea className="flex-1 mb-4">
          <div className="space-y-4 pr-2">
            {activeTurns.map((turn) => (
              <TurnCard key={turn.id} turn={turn} />
            ))}

            {/* Streaming Progress (current turn being generated) */}
            {isActive && (
              <Card>
                <CardContent className="py-4 space-y-3">
                  <div className="flex items-center gap-2">
                    <Radio className="h-3 w-3 text-primary animate-pulse" />
                    <span className="text-sm text-muted-foreground">
                      {STATUS_LABELS[stream.status] ?? stream.status}
                    </span>
                  </div>

                  {stream.classification && (
                    <div className="flex items-center gap-2">
                      <Badge
                        variant={stream.classification.type === "needs_workflow" ? "default" : "secondary"}
                        className="text-xs"
                      >
                        {stream.classification.type === "needs_workflow" ? (
                          <>
                            <Workflow className="mr-1 h-3 w-3" />
                            {stream.classification.workflow_type} Recommended
                          </>
                        ) : (
                          <>
                            <Brain className="mr-1 h-3 w-3" />
                            Direct Answer
                          </>
                        )}
                      </Badge>
                      {stream.classification.target_agent && (
                        <Badge variant="outline" className="text-xs">
                          <User className="mr-1 h-3 w-3" />
                          {stream.classification.target_agent}
                        </Badge>
                      )}
                    </div>
                  )}

                  {stream.streamedText && (
                    <div className="mt-2">
                      <p className="text-xs font-medium text-muted-foreground mb-1">Answer</p>
                      <p className="text-sm leading-relaxed whitespace-pre-wrap">
                        {stream.streamedText}
                        <span className="inline-block w-1.5 h-4 bg-primary/60 animate-pulse ml-0.5 align-text-bottom" />
                      </p>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            {/* Workflow recommendation (no turns created for workflow queries) */}
            {stream.status === "done" && stream.classification && (
              <StreamResult classification={stream.classification} />
            )}

            {/* Empty state when no conversation and idle */}
            {activeTurns.length === 0 && !isActive && stream.status !== "done" && (
              <div className="flex items-center justify-center h-48 text-muted-foreground">
                <div className="text-center space-y-2">
                  <MessageSquare className="h-8 w-8 mx-auto opacity-30" />
                  <p className="text-sm">Start a conversation by asking a research question below</p>
                </div>
              </div>
            )}
            <div ref={scrollBottomRef} />
          </div>
        </ScrollArea>

        {/* Error */}
        {stream.error && (
          <Card className="border-destructive mb-4">
            <CardContent className="py-3">
              <p className="text-sm text-destructive">{stream.error}</p>
            </CardContent>
          </Card>
        )}

        {/* Query Input (pinned to bottom) */}
        <Card className="shrink-0">
          <CardContent className="pt-4 pb-3">
            <div className="space-y-2">
              <Textarea
                id="query-input"
                placeholder={
                  activeConvId
                    ? "Ask a follow-up question..."
                    : "e.g., What are the key mechanisms of spaceflight-induced anemia?"
                }
                className="min-h-[80px] text-sm resize-none"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={isActive}
                aria-label="Enter your research question"
              />
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">
                  {query.length}/2000 | Cmd+Enter to submit
                  {activeConvId && (
                    <span className="ml-2 text-primary">
                      Continuing conversation ({activeTurns.length} turn{activeTurns.length !== 1 ? "s" : ""})
                    </span>
                  )}
                </span>
                <Button
                  onClick={handleSubmit}
                  disabled={isActive || !query.trim()}
                  size="sm"
                >
                  {isActive ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Send className="mr-2 h-4 w-4" />
                  )}
                  {isActive ? "Analyzing..." : "Ask"}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function TurnCard({ turn }: { turn: ConversationTurn }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    const md = `**Q:** ${turn.query}\n\n**A:** ${turn.answer ?? ""}`;
    void navigator.clipboard.writeText(md).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [turn.query, turn.answer]);

  return (
    <div className="space-y-2">
      {/* User query */}
      <div className="flex justify-end">
        <div className="rounded-lg bg-primary/10 px-3 py-2 max-w-[80%]">
          <p className="text-sm">{turn.query}</p>
        </div>
      </div>
      {/* Assistant answer */}
      {turn.answer && (
        <Card>
          <CardContent className="py-3 space-y-3">
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-2">
                {turn.routed_agent && (
                  <Badge variant="outline" className="text-xs">
                    <User className="mr-1 h-3 w-3" />
                    {turn.routed_agent}
                  </Badge>
                )}
                <span className="text-xs text-muted-foreground flex items-center gap-1">
                  <DollarSign className="h-3 w-3" />${turn.cost.toFixed(4)}
                </span>
                <span className="text-xs text-muted-foreground flex items-center gap-1">
                  <Clock className="h-3 w-3" />{(turn.duration_ms / 1000).toFixed(1)}s
                </span>
              </div>
              <Button variant="ghost" size="sm" className="h-6 px-2 text-xs" onClick={handleCopy}>
                {copied ? <Check className="h-3 w-3 mr-1 text-emerald-500" /> : <Copy className="h-3 w-3 mr-1" />}
                {copied ? "Copied" : "Copy"}
              </Button>
            </div>
            <p className="text-sm leading-relaxed whitespace-pre-wrap">{turn.answer}</p>
            {(turn.ungrounded_citations?.length ?? 0) > 0 && (
              <div className="flex items-start gap-1.5 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-700">
                <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                <div>
                  <span className="font-medium">Unverified citations</span> — the following
                  identifiers in the answer could not be matched to retrieved sources:{" "}
                  <span className="font-mono">{turn.ungrounded_citations!.join(", ")}</span>
                </div>
              </div>
            )}
            <SourcesList sources={turn.sources} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function StreamResult({
  classification,
}: {
  classification: { type: string; reasoning: string; target_agent: string | null; workflow_type: string | null };
}) {
  if (classification.type !== "needs_workflow") return null;

  return (
    <Card>
      <CardContent className="py-4">
        <div className="rounded-md border border-border bg-accent/50 p-3">
          <p className="text-xs font-medium mb-1">Recommended Workflow</p>
          <p className="text-sm">
            This question requires a <strong>{classification.workflow_type}</strong> workflow for
            comprehensive analysis. Create one from the{" "}
            <Link href="/" className="text-primary underline">Mission Control</Link> page.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function SourcesList({ sources }: { sources: Record<string, unknown>[] }) {
  if (!sources || sources.length === 0) return null;

  return (
    <>
      <Separator />
      <div>
        <p className="text-xs font-medium text-muted-foreground mb-1 flex items-center gap-1">
          <BookOpen className="h-3 w-3" />
          Sources ({sources.length})
        </p>
        <div className="space-y-1.5">
          {sources.map((src, i) => {
            const doi = src.doi ? String(src.doi) : null;
            const pmid = src.pmid ? String(src.pmid) : null;
            const doiUrl = doi ? `https://doi.org/${doi}` : null;
            const pmidUrl = pmid ? `https://pubmed.ncbi.nlm.nih.gov/${pmid}/` : null;
            const authors = Array.isArray(src.authors)
              ? (src.authors as string[]).slice(0, 3).join(", ") + (src.authors.length > 3 ? " et al." : "")
              : null;

            return (
              <div key={i} className="rounded border border-border bg-accent/20 p-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    {src.title ? (
                      doiUrl ? (
                        <a
                          href={doiUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs font-medium hover:underline text-foreground flex items-center gap-1 group"
                        >
                          <span className="truncate">{String(src.title)}</span>
                          <ExternalLink className="h-2.5 w-2.5 shrink-0 opacity-0 group-hover:opacity-70" />
                        </a>
                      ) : (
                        <p className="text-xs font-medium truncate">{String(src.title)}</p>
                      )
                    ) : null}
                    {authors && (
                      <p className="text-xs text-muted-foreground mt-0.5">{authors}</p>
                    )}
                    {src.content_snippet ? (
                      <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                        {String(src.content_snippet)}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {src.year ? (
                      <Badge variant="outline" className="text-xs">{String(src.year)}</Badge>
                    ) : null}
                    {src.source_type ? (
                      <Badge variant="secondary" className="text-xs">{String(src.source_type)}</Badge>
                    ) : null}
                  </div>
                </div>
                <div className="flex items-center gap-2 mt-1">
                  {doiUrl && (
                    <a
                      href={doiUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-muted-foreground hover:text-primary font-mono flex items-center gap-0.5"
                    >
                      DOI: {doi}
                    </a>
                  )}
                  {pmidUrl && (
                    <a
                      href={pmidUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-muted-foreground hover:text-primary flex items-center gap-0.5"
                    >
                      PMID: {pmid}
                    </a>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}
