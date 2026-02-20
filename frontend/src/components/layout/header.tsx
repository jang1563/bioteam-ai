"use client";

import { useEffect, useState } from "react";
import { Activity, Wifi, WifiOff } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api-client";
import type { HealthResponse } from "@/types/api";

export function Header() {
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    const check = async () => {
      try {
        const data = await api.get<HealthResponse>("/health");
        setHealth(data);
      } catch {
        setHealth(null);
      }
    };
    check();
    const interval = setInterval(check, 30_000);
    return () => clearInterval(interval);
  }, []);

  const isHealthy = health?.status === "healthy";

  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-background px-6">
      <div className="flex items-center gap-2">
        <Activity className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        <span className="text-sm font-medium text-muted-foreground">
          Dashboard
        </span>
      </div>

      <div className="flex items-center gap-3">
        <Badge
          variant={isHealthy ? "default" : "destructive"}
          className="flex items-center gap-1.5 text-xs"
          role="status"
          aria-live="polite"
          aria-label={`Backend status: ${isHealthy ? "Connected" : "Disconnected"}`}
        >
          {isHealthy ? (
            <Wifi className="h-3 w-3" aria-hidden="true" />
          ) : (
            <WifiOff className="h-3 w-3" aria-hidden="true" />
          )}
          {isHealthy ? "Connected" : "Disconnected"}
        </Badge>
        {health && (
          <span className="text-xs text-muted-foreground">
            v{health.version}
          </span>
        )}
      </div>
    </header>
  );
}
