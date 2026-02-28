"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, X } from "lucide-react";
import { Sidebar } from "./sidebar";
import { Header } from "./header";
import { ErrorBoundary } from "./error-boundary";

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [authError, setAuthError] = useState<string | null>(null);

  useEffect(() => {
    const handler = (e: Event) => {
      const { status } = (e as CustomEvent<{ status: number; path: string }>).detail;
      setAuthError(
        status === 401
          ? "Unauthorized — check your API key in Settings."
          : "Access forbidden — check your API key in Settings.",
      );
      router.push("/settings");
    };
    window.addEventListener("bioteam:auth-error", handler);
    return () => window.removeEventListener("bioteam:auth-error", handler);
  }, [router]);

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Skip-to-content for keyboard users */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded-md focus:bg-background focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:ring-2 focus:ring-ring focus:outline-none"
      >
        Skip to main content
      </a>
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header />
        {authError && (
          <div
            role="alert"
            className="flex items-center gap-2 border-b border-destructive/30 bg-destructive/10 px-6 py-2 text-xs text-destructive"
          >
            <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <span className="flex-1">{authError}</span>
            <button
              onClick={() => setAuthError(null)}
              aria-label="Dismiss"
              className="rounded p-0.5 hover:bg-destructive/20"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        )}
        <main id="main-content" className="flex-1 overflow-y-auto p-6">
          <ErrorBoundary>{children}</ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
