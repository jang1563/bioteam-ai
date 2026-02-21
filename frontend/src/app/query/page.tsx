"use client";

import React, { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { Send, Loader2, Brain, Workflow, Clock, DollarSign } from "lucide-react";
import { api } from "@/lib/api-client";
import type { DirectQueryResponse } from "@/types/api";

export default function QueryPage() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DirectQueryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<DirectQueryResponse[]>([]);

  const handleSubmit = async () => {
    if (!query.trim() || loading) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.post<DirectQueryResponse>("/api/v1/direct-query", {
        query: query.trim(),
      });
      setResult(res);
      setHistory((prev) => [res, ...prev].slice(0, 20));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Query failed");
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Direct Query</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Ask a research question. The Research Director will classify it and route to the appropriate agent or workflow.
        </p>
      </div>

      {/* Query Input */}
      <Card>
        <CardContent className="pt-6">
          <div className="space-y-3">
            <label htmlFor="query-input" className="text-sm font-medium">
              Research Question
            </label>
            <Textarea
              id="query-input"
              placeholder="e.g., What are the key mechanisms of spaceflight-induced anemia?"
              className="min-h-[100px] text-sm"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
              aria-label="Enter your research question"
            />
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">
                {query.length}/2000 characters | Cmd+Enter to submit
              </span>
              <Button
                onClick={handleSubmit}
                disabled={loading || !query.trim()}
                size="sm"
              >
                {loading ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Send className="mr-2 h-4 w-4" />
                )}
                {loading ? "Analyzing..." : "Ask"}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <Card className="border-destructive">
          <CardContent className="py-4">
            <p className="text-sm text-destructive">{error}</p>
          </CardContent>
        </Card>
      )}

      {/* Loading */}
      {loading && (
        <Card>
          <CardContent className="py-8 text-center">
            <Loader2 className="mx-auto h-8 w-8 animate-spin text-muted-foreground" />
            <p className="mt-3 text-sm text-muted-foreground">
              Research Director is analyzing your query...
            </p>
          </CardContent>
        </Card>
      )}

      {/* Result */}
      {result && <QueryResult result={result} />}

      {/* History */}
      {history.length > 1 && (
        <div className="space-y-3">
          <h2 className="text-sm font-medium text-muted-foreground">
            Previous Queries ({history.length - 1})
          </h2>
          {history.slice(1).map((r, i) => (
            <Card key={i} className="opacity-70 hover:opacity-100 transition-opacity">
              <CardContent className="py-3">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium truncate">{r.query}</p>
                    <div className="mt-1 flex items-center gap-2">
                      <Badge variant="outline" className="text-xs">
                        {r.classification_type === "needs_workflow" ? r.workflow_type : "Direct"}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        ${r.total_cost.toFixed(4)}
                      </span>
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-xs shrink-0"
                    onClick={() => {
                      setResult(r);
                      window.scrollTo({ top: 0, behavior: "smooth" });
                    }}
                  >
                    View
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function QueryResult({ result }: { result: DirectQueryResponse }) {
  const isWorkflow = result.classification_type === "needs_workflow";

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">Analysis Result</CardTitle>
          <div className="flex items-center gap-2">
            <Badge
              variant={isWorkflow ? "default" : "secondary"}
              className="text-xs"
            >
              {isWorkflow ? (
                <>
                  <Workflow className="mr-1 h-3 w-3" />
                  {result.workflow_type} Recommended
                </>
              ) : (
                <>
                  <Brain className="mr-1 h-3 w-3" />
                  Direct Answer
                </>
              )}
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Query */}
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-1">Question</p>
          <p className="text-sm">{result.query}</p>
        </div>

        <Separator />

        {/* Classification Reasoning */}
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-1">
            Research Director Analysis
          </p>
          <p className="text-sm leading-relaxed text-muted-foreground">
            {result.classification_reasoning}
          </p>
        </div>

        {/* Direct Answer (for simple queries) */}
        {result.answer && (
          <>
            <Separator />
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-1">Answer</p>
              <p className="text-sm leading-relaxed whitespace-pre-wrap">{result.answer}</p>
            </div>
          </>
        )}

        {/* Workflow recommendation */}
        {isWorkflow && result.workflow_type && (
          <>
            <Separator />
            <div className="rounded-md border border-border bg-accent/50 p-3">
              <p className="text-xs font-medium mb-1">Recommended Workflow</p>
              <p className="text-sm">
                This question requires a <strong>{result.workflow_type}</strong> workflow for
                comprehensive analysis. Create one from the{" "}
                <a href="/" className="text-primary underline">Mission Control</a> page.
              </p>
              {result.target_agent && (
                <p className="text-xs text-muted-foreground mt-1">
                  Primary agent: {result.target_agent}
                </p>
              )}
            </div>
          </>
        )}

        {/* Memory Context */}
        {result.memory_context.length > 0 && (
          <>
            <Separator />
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-1">
                Related Knowledge ({result.memory_context.length})
              </p>
              <div className="space-y-1">
                {result.memory_context.map((ctx, i) => (
                  <div key={i} className="rounded bg-accent/30 p-2 text-xs">
                    {JSON.stringify(ctx).slice(0, 200)}
                  </div>
                ))}
              </div>
            </div>
          </>
        )}

        <Separator />

        {/* Metadata */}
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <DollarSign className="h-3 w-3" />
            ${result.total_cost.toFixed(4)}
          </span>
          <span className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {(result.duration_ms / 1000).toFixed(1)}s
          </span>
          <span>{result.total_tokens.toLocaleString()} tokens</span>
          <span className="font-mono">{result.model_versions.join(", ")}</span>
        </div>
      </CardContent>
    </Card>
  );
}
