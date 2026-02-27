"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { api } from "@/lib/api-client";
import type { HealthResponse, ColdStartStatus, ColdStartResponse, ColdStartRequest } from "@/types/api";
import {
  Key, Server, CheckCircle2, XCircle, Rocket, Loader2,
  Database, BookOpen, FlaskConical, AlertTriangle,
} from "lucide-react";

export default function SettingsPage() {
  const [apiKey, setApiKey] = useState(() => (
    typeof window !== "undefined"
      ? (localStorage.getItem("bioteam_api_key") ?? "")
      : ""
  ));
  const [saved, setSaved] = useState(false);
  const [health, setHealth] = useState<HealthResponse | null>(null);

  const checkHealth = useCallback(async () => {
    try {
      const data = await api.get<HealthResponse>("/health");
      setHealth(data);
    } catch {
      setHealth(null);
    }
  }, []);

  useEffect(() => {
    const id = window.setTimeout(() => {
      void checkHealth();
    }, 0);
    return () => window.clearTimeout(id);
  }, [checkHealth]);

  const saveKey = () => {
    if (apiKey.trim()) {
      localStorage.setItem("bioteam_api_key", apiKey.trim());
    } else {
      localStorage.removeItem("bioteam_api_key");
    }
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Settings</h1>

      {/* API Key */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            <Key className="h-4 w-4" /> API Key
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xs text-muted-foreground">
            Set your BioTeam-AI API key for authenticated requests.
            Leave empty for dev mode (no auth).
          </p>
          <div className="flex gap-2">
            <Input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="Enter API key..."
              className="flex-1"
            />
            <Button onClick={saveKey} size="sm">
              {saved ? "Saved!" : "Save"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Cold Start Controls */}
      <ColdStartCard />

      {/* Backend Status */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            <Server className="h-4 w-4" /> Backend Status
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center gap-2">
            {health ? (
              <Badge variant="default" className="flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3" /> {health.status}
              </Badge>
            ) : (
              <Badge variant="destructive" className="flex items-center gap-1">
                <XCircle className="h-3 w-3" /> Disconnected
              </Badge>
            )}
            {health && (
              <span className="text-xs text-muted-foreground">v{health.version}</span>
            )}
          </div>

          {health?.dependencies && (
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground">Dependencies</p>
              {Object.entries(health.dependencies).map(([k, v]) => (
                <div key={k} className="flex items-center justify-between text-xs">
                  <span>{k}</span>
                  <Badge
                    variant={v === "healthy" || v === "ok" ? "default" : "destructive"}
                    className="text-xs"
                  >
                    {v}
                  </Badge>
                </div>
              ))}
            </div>
          )}

          <Button size="sm" variant="outline" onClick={checkHealth}>
            Refresh
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

function ColdStartCard() {
  const [status, setStatus] = useState<ColdStartStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState<"quick" | "full" | null>(null);
  const [result, setResult] = useState<ColdStartResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [seedQueries, setSeedQueries] = useState("spaceflight biology, space anemia");

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
    setRunning("quick");
    setError(null);
    setResult(null);
    try {
      const res = await api.post<ColdStartResponse>("/api/v1/cold-start/quick");
      setResult(res);
      await fetchStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Quick Start failed");
    } finally {
      setRunning(null);
    }
  };

  const handleFullColdStart = async () => {
    setRunning("full");
    setError(null);
    setResult(null);
    try {
      const queries = seedQueries
        .split(",")
        .map((q) => q.trim())
        .filter(Boolean);
      const body: ColdStartRequest = {
        seed_queries: queries.length > 0 ? queries : undefined,
      };
      const res = await api.post<ColdStartResponse>("/api/v1/cold-start/run", body);
      setResult(res);
      await fetchStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Cold Start failed");
    } finally {
      setRunning(null);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <Rocket className="h-4 w-4" /> Cold Start / Setup
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Current Status */}
        {loading ? (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" /> Checking status...
          </div>
        ) : status ? (
          <div className="space-y-2">
            <div className="flex flex-wrap gap-2">
              <Badge
                variant={status.is_initialized ? "default" : "destructive"}
                className="text-xs flex items-center gap-1"
              >
                {status.is_initialized ? (
                  <CheckCircle2 className="h-3 w-3" />
                ) : (
                  <XCircle className="h-3 w-3" />
                )}
                {status.is_initialized ? "Initialized" : "Not Initialized"}
              </Badge>
              <Badge
                variant={status.critical_agents_healthy ? "default" : "destructive"}
                className="text-xs flex items-center gap-1"
              >
                {status.agents_registered} agents
              </Badge>
              <Badge
                variant={status.has_literature ? "default" : "outline"}
                className="text-xs flex items-center gap-1"
              >
                <BookOpen className="h-3 w-3" />
                {status.has_literature
                  ? `${status.collection_counts?.literature ?? 0} literature`
                  : "No literature"}
              </Badge>
              <Badge
                variant={status.has_lab_kb ? "default" : "outline"}
                className="text-xs flex items-center gap-1"
              >
                <FlaskConical className="h-3 w-3" />
                {status.has_lab_kb
                  ? `${status.collection_counts?.lab_kb ?? 0} lab KB`
                  : "No Lab KB"}
              </Badge>
              <Badge variant="outline" className="text-xs flex items-center gap-1">
                <Database className="h-3 w-3" />
                {status.total_documents} total docs
              </Badge>
            </div>
          </div>
        ) : (
          <p className="text-xs text-muted-foreground flex items-center gap-1.5">
            <AlertTriangle className="h-3 w-3 text-destructive" />
            Backend not reachable
          </p>
        )}

        <Separator />

        {/* Quick Start */}
        <div>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Quick Start</p>
              <p className="text-xs text-muted-foreground">
                Verify agents only (skip literature seeding). See value immediately.
              </p>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={handleQuickStart}
              disabled={running !== null}
            >
              {running === "quick" ? (
                <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />
              ) : (
                <Rocket className="mr-1.5 h-3 w-3" />
              )}
              Quick Start
            </Button>
          </div>
        </div>

        <Separator />

        {/* Full Cold Start */}
        <div className="space-y-3">
          <div>
            <p className="text-sm font-medium">Full Cold Start</p>
            <p className="text-xs text-muted-foreground">
              Seed literature from PubMed + Semantic Scholar, then run smoke test.
            </p>
          </div>
          <div>
            <label htmlFor="seed-queries" className="text-xs font-medium text-muted-foreground">
              Seed Queries (comma-separated)
            </label>
            <Input
              id="seed-queries"
              value={seedQueries}
              onChange={(e) => setSeedQueries(e.target.value)}
              placeholder="spaceflight biology, space anemia"
              className="mt-1 text-sm"
              disabled={running !== null}
            />
          </div>
          <Button
            size="sm"
            onClick={handleFullColdStart}
            disabled={running !== null}
          >
            {running === "full" ? (
              <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />
            ) : (
              <Database className="mr-1.5 h-3 w-3" />
            )}
            Run Full Cold Start
          </Button>
        </div>

        {/* Error */}
        {error && (
          <p className="text-xs text-destructive">{error}</p>
        )}

        {/* Result */}
        {result && (
          <>
            <Separator />
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Badge variant={result.success ? "default" : "destructive"} className="text-xs">
                  {result.success ? "Success" : "Failed"}
                </Badge>
                <span className="text-xs text-muted-foreground">
                  {result.mode} mode | {(result.duration_ms / 1000).toFixed(1)}s
                </span>
              </div>
              <p className="text-xs">{result.message}</p>
              {result.seed_results.length > 0 && (
                <div className="space-y-1">
                  <p className="text-xs font-medium text-muted-foreground">Seeding Results</p>
                  {result.seed_results.map((sr, i) => (
                    <div key={i} className="flex items-center justify-between text-xs">
                      <span className="font-mono">
                        {sr.source}: &quot;{sr.query}&quot;
                      </span>
                      <span>
                        {sr.papers_stored} stored / {sr.papers_fetched} fetched
                      </span>
                    </div>
                  ))}
                </div>
              )}
              {result.smoke_checks.length > 0 && (
                <div className="space-y-1">
                  <p className="text-xs font-medium text-muted-foreground">Smoke Checks</p>
                  {result.smoke_checks.map((sc, i) => (
                    <div key={i} className="flex items-center justify-between text-xs">
                      <span>{sc.name}</span>
                      <Badge
                        variant={sc.passed ? "default" : "destructive"}
                        className="text-xs"
                      >
                        {sc.passed ? "Pass" : "Fail"}
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
