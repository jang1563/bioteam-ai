"use client";

import { useEffect, useState } from "react";
import { Activity, Wifi, WifiOff, AlertTriangle } from "lucide-react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api-client";
import type { HealthResponse } from "@/types/api";

export function Header() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [isDevMode] = useState(() =>
    typeof window !== "undefined" ? !localStorage.getItem("bioteam_api_key") : false,
  );

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
    <>
      <header className="flex h-14 items-center justify-between border-b border-border bg-background px-6">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <span className="text-sm font-medium text-muted-foreground">
            Dashboard
          </span>
        </div>

        <div className="flex items-center gap-3">
          {isDevMode && (
            <Badge variant="outline" className="flex items-center gap-1 text-[10px] border-amber-500/50 text-amber-500">
              <AlertTriangle className="h-2.5 w-2.5" aria-hidden="true" />
              Dev Mode
            </Badge>
          )}
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
      {isDevMode && (
        <div className="border-b border-amber-500/20 bg-amber-500/5 px-6 py-1.5 text-[11px] text-amber-600">
          <AlertTriangle className="mr-1.5 inline h-3 w-3" aria-hidden="true" />
          Dev mode — Authentication disabled.{" "}
          <Link href="/settings" className="underline underline-offset-2 hover:text-amber-700">
            Set your API key in Settings
          </Link>{" "}
          to enable auth.
        </div>
      )}
    </>
  );
}
