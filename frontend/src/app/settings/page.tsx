"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api-client";
import type { HealthResponse } from "@/types/api";
import { Key, Server, CheckCircle2, XCircle } from "lucide-react";

export default function SettingsPage() {
  const [apiKey, setApiKey] = useState("");
  const [saved, setSaved] = useState(false);
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    const stored = localStorage.getItem("bioteam_api_key") ?? "";
    setApiKey(stored);
    checkHealth();
  }, []);

  const checkHealth = async () => {
    try {
      const data = await api.get<HealthResponse>("/health");
      setHealth(data);
    } catch {
      setHealth(null);
    }
  };

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
