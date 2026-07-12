"use client";

import { useRef, useState, useCallback } from "react";
import { X, Send, Radio, Trash2 } from "lucide-react";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { getAgentCharacter, AGENT_COLOR_CLASSES } from "@/lib/agent-characters";
import { useAgentStream } from "@/hooks/use-agent-stream";
import { useAgentDetail } from "@/hooks/use-agents";
import type { AgentStreamSource } from "@/hooks/use-agent-stream";

// ── Types ─────────────────────────────────────────────────────────────────────

interface ChatMessage {
  id: string;
  role: "user" | "agent";
  content: string;
  timestamp: Date;
  sources?: AgentStreamSource[];
}

interface AgentChatSheetProps {
  agentId: string | null;
  onClose: () => void;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const STATE_BADGE: Record<
  string,
  { label: string; variant: "default" | "secondary" | "destructive" | "outline" }
> = {
  idle: { label: "Idle", variant: "secondary" },
  busy: { label: "Busy", variant: "default" },
  unavailable: { label: "Unavailable", variant: "destructive" },
  unknown: { label: "Unknown", variant: "outline" },
};

const MAX_CHARS = 2000;

// ── Component ─────────────────────────────────────────────────────────────────

const MAX_STORED = 20;

function storageKey(id: string) {
  return `agent-chat:${id}`;
}

function loadMessages(id: string): ChatMessage[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(storageKey(id));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Array<Omit<ChatMessage, "timestamp"> & { timestamp: string }>;
    return parsed.slice(-MAX_STORED).map((m) => ({ ...m, timestamp: new Date(m.timestamp) }));
  } catch {
    return [];
  }
}

export function AgentChatSheet({ agentId, onClose }: AgentChatSheetProps) {
  const [messages, setMessages] = useState<ChatMessage[]>(() =>
    agentId ? loadMessages(agentId) : [],
  );
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const [wasRestored, setWasRestored] = useState(() =>
    agentId ? loadMessages(agentId).length > 0 : false,
  );

  const { agent } = useAgentDetail(agentId);
  const { status, streamedText, error, execute } = useAgentStream(agentId);

  // Adjust state when agentId prop changes (React-recommended render-time pattern)
  const [prevAgentId, setPrevAgentId] = useState(agentId);
  if (agentId !== prevAgentId) {
    setPrevAgentId(agentId);
    if (!agentId) {
      setMessages([]);
      setWasRestored(false);
    } else {
      const stored = loadMessages(agentId);
      setMessages(stored);
      setWasRestored(stored.length > 0);
    }
  }

  const saveToStorage = useCallback((msgs: ChatMessage[]) => {
    if (typeof window === "undefined" || !agentId) return;
    try {
      localStorage.setItem(storageKey(agentId), JSON.stringify(msgs.slice(-MAX_STORED)));
    } catch { /* private browsing or storage full */ }
  }, [agentId]);

  const clearHistory = useCallback(() => {
    setMessages([]);
    setWasRestored(false);
    if (agentId) localStorage.removeItem(storageKey(agentId));
  }, [agentId]);

  const character = agentId ? getAgentCharacter(agentId) : null;
  const colors = character ? AGENT_COLOR_CLASSES[character.color] : null;
  const Icon = character?.icon ?? null;
  const agentState = agent?.state ?? "unknown";
  const stateBadge = STATE_BADGE[agentState] ?? STATE_BADGE.unknown;

  const scrollToBottom = useCallback(() => {
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
  }, []);

  const handleSubmit = useCallback(async () => {
    const query = input.trim();
    if (
      !query ||
      status === "streaming" ||
      status === "classifying" ||
      status === "retrieving"
    ) return;

    // Add user message immediately
    setMessages((prev) => {
      const next = [...prev, { id: crypto.randomUUID(), role: "user" as const, content: query, timestamp: new Date() }];
      saveToStorage(next);
      return next;
    });
    setInput("");
    scrollToBottom();

    try {
      // execute() resolves with final text + sources when streaming completes
      const result = await execute(query);
      if (result.text) {
        setMessages((prev) => {
          const next = [
            ...prev,
            {
              id: crypto.randomUUID(),
              role: "agent" as const,
              content: result.text,
              timestamp: new Date(),
              sources: result.sources.length > 0 ? result.sources : undefined,
            },
          ];
          saveToStorage(next);
          return next;
        });
        scrollToBottom();
      }
    } catch {
      // Error state is handled by the hook's `error` value
    }
  }, [input, status, execute, scrollToBottom, saveToStorage]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  const isStreaming =
    status === "classifying" || status === "retrieving" || status === "streaming";
  const charsLeft = MAX_CHARS - input.length;

  return (
    <Sheet open={!!agentId} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        side="right"
        showCloseButton={false}
        className="flex w-full flex-col p-0 sm:max-w-[600px]"
        aria-label={agent ? `Chat with ${agent.name}` : "Agent chat"}
      >
        {/* ── Header ── */}
        <SheetHeader className="flex-row items-start gap-3 border-b border-border px-5 py-4">
          {Icon && colors && (
            <div
              className={cn(
                "flex h-12 w-12 shrink-0 items-center justify-center rounded-full ring-1",
                colors.bg,
                colors.ring,
              )}
              aria-hidden="true"
            >
              <Icon className={cn("h-6 w-6", colors.text)} strokeWidth={1.5} />
            </div>
          )}
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <SheetTitle className="truncate text-base font-semibold">
                {agent?.name ?? agentId ?? "Agent"}
              </SheetTitle>
              <Badge variant={stateBadge.variant} className="shrink-0 text-[10px]">
                {stateBadge.label}
              </Badge>
            </div>
            {character && (
              <p className="mt-0.5 text-xs italic text-muted-foreground">
                {character.tagline}
              </p>
            )}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            {messages.length > 0 && (
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-muted-foreground hover:text-destructive"
                onClick={clearHistory}
                aria-label="Clear chat history"
                title="Clear history"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            )}
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 shrink-0"
              onClick={onClose}
              aria-label="Close chat"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </SheetHeader>

        {/* ── Messages ── */}
        <ScrollArea className="flex-1 px-4">
          <div className="flex flex-col gap-4 py-4">
            {/* Empty state */}
            {messages.length === 0 && !isStreaming && (
              <div className="flex flex-col items-center gap-2 py-12 text-center text-muted-foreground">
                {Icon && colors && (
                  <div
                    className={cn(
                      "flex h-14 w-14 items-center justify-center rounded-full",
                      colors.bg,
                    )}
                  >
                    <Icon className={cn("h-7 w-7", colors.text)} strokeWidth={1.5} />
                  </div>
                )}
                <p className="text-sm font-medium">{agent?.name ?? "Agent"}</p>
                <p className="max-w-xs text-xs">{character?.tagline}</p>
                <p className="mt-1 text-xs text-muted-foreground/60">
                  Ask a research question to get started.
                </p>
              </div>
            )}

            {/* Restored history indicator */}
            {wasRestored && messages.length > 0 && (
              <div className="flex items-center gap-2 text-[10px] text-muted-foreground/60">
                <div className="h-px flex-1 bg-border/50" />
                <span>previous session</span>
                <div className="h-px flex-1 bg-border/50" />
              </div>
            )}

            {/* Message history */}
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={cn(
                  "flex flex-col gap-1",
                  msg.role === "user" ? "items-end" : "items-start",
                )}
              >
                <div
                  className={cn(
                    "max-w-[85%] rounded-lg px-3 py-2 text-sm",
                    msg.role === "user"
                      ? "bg-primary/10 text-foreground"
                      : "bg-accent text-foreground",
                  )}
                >
                  <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                </div>

                {/* Sources */}
                {msg.sources && msg.sources.length > 0 && (
                  <div className="mt-1 max-w-[85%] space-y-1">
                    <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
                      {msg.sources.length} source{msg.sources.length !== 1 ? "s" : ""}
                    </p>
                    {msg.sources.slice(0, 3).map((src, i) => (
                      <div
                        key={i}
                        className="rounded-md border border-border bg-accent/30 px-2.5 py-1.5 text-[11px]"
                      >
                        <p className="line-clamp-1 font-medium">
                          {src.title ?? "Untitled"}
                        </p>
                        <div className="mt-0.5 flex flex-wrap gap-1.5">
                          {src.year && (
                            <Badge
                              variant="outline"
                              className="h-4 px-1 py-0 text-[9px]"
                            >
                              {src.year}
                            </Badge>
                          )}
                          {src.source_type && (
                            <Badge
                              variant="outline"
                              className="h-4 px-1 py-0 text-[9px]"
                            >
                              {src.source_type}
                            </Badge>
                          )}
                          {src.doi && (
                            <span className="font-mono text-[9px] text-muted-foreground">
                              {src.doi}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                    {msg.sources.length > 3 && (
                      <p className="text-[10px] text-muted-foreground">
                        +{msg.sources.length - 3} more
                      </p>
                    )}
                  </div>
                )}

                <span className="text-[9px] text-muted-foreground/50">
                  {msg.timestamp.toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              </div>
            ))}

            {/* Streaming in-progress */}
            {isStreaming && (
              <div className="flex flex-col items-start gap-1">
                {(status === "classifying" || status === "retrieving") && (
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <Radio className="h-3 w-3 animate-pulse" aria-hidden="true" />
                    {status === "classifying" ? "Routing…" : "Retrieving context…"}
                  </div>
                )}
                {streamedText && (
                  <div className="max-w-[85%] rounded-lg bg-accent px-3 py-2 text-sm">
                    <p className="whitespace-pre-wrap leading-relaxed">
                      {streamedText}
                      <span className="ml-0.5 inline-block h-[1em] w-[2px] animate-pulse bg-foreground align-text-bottom" />
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* Error */}
            {error && status === "error" && (
              <div className="rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">
                {error}
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        </ScrollArea>

        <Separator />

        {/* ── Input ── */}
        <div className="p-4">
          <div className="relative">
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value.slice(0, MAX_CHARS))}
              onKeyDown={handleKeyDown}
              placeholder={`Ask ${agent?.name ?? "the agent"} a research question…`}
              rows={3}
              disabled={isStreaming}
              aria-label="Research question"
              className="resize-none pr-10 text-sm"
            />
            <Button
              size="icon"
              className="absolute bottom-2 right-2 h-7 w-7"
              onClick={handleSubmit}
              disabled={!input.trim() || isStreaming}
              aria-label="Send message"
            >
              <Send className="h-3.5 w-3.5" />
            </Button>
          </div>
          <div className="mt-1.5 flex items-center justify-between">
            <p className="text-[10px] text-muted-foreground">
              {isStreaming ? "Streaming…" : "⌘+Enter to send"}
            </p>
            <p
              className={cn(
                "text-[10px]",
                charsLeft < 200 ? "text-amber-500" : "text-muted-foreground/50",
              )}
            >
              {charsLeft}
            </p>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
