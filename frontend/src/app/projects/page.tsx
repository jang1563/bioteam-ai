"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { FolderKanban } from "lucide-react";

export default function ProjectsPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">Projects</h1>
        <Badge variant="outline" className="text-xs">Coming Soon</Badge>
      </div>

      <Card className="border-dashed">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <FolderKanban className="h-4 w-4" />
            Project Management
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Multi-project support with task tracking is planned for Phase 2.
            Currently all workflows run under a single default project context.
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <InfoCard title="Workflows" desc="Create and manage research workflows from Mission Control" />
            <InfoCard title="Tasks" desc="Track individual research tasks within projects" />
            <InfoCard title="Collaboration" desc="Multi-user project sharing (Phase 3)" />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function InfoCard({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="rounded-lg border border-border p-4">
      <p className="text-sm font-medium">{title}</p>
      <p className="mt-1 text-xs text-muted-foreground">{desc}</p>
    </div>
  );
}
