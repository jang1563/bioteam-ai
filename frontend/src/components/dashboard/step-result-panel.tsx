"use client";

export function StepResultPanel({ data }: { data: Record<string, unknown> }) {
  return (
    <div className="ml-6 mb-2 rounded border border-border bg-accent/30 p-2 text-xs space-y-1.5">
      {Object.entries(data).map(([key, value]) => {
        if (value === null || value === undefined) return null;
        const displayKey = key.replace(/_/g, " ");

        if (typeof value === "string" && value.length > 100) {
          return (
            <div key={key}>
              <span className="font-medium text-muted-foreground capitalize">{displayKey}:</span>
              <p className="mt-0.5 whitespace-pre-wrap text-[11px] leading-relaxed max-h-[200px] overflow-y-auto">
                {value}
              </p>
            </div>
          );
        }

        if (Array.isArray(value)) {
          return (
            <div key={key}>
              <span className="font-medium text-muted-foreground capitalize">
                {displayKey} ({value.length}):
              </span>
              <div className="mt-0.5 space-y-0.5">
                {value.slice(0, 10).map((item, i) => (
                  <div key={i} className="text-[11px] pl-2 border-l border-border">
                    {typeof item === "object" ? JSON.stringify(item).slice(0, 200) : String(item)}
                  </div>
                ))}
                {value.length > 10 && (
                  <span className="text-muted-foreground text-[10px]">
                    ...and {value.length - 10} more
                  </span>
                )}
              </div>
            </div>
          );
        }

        if (typeof value === "object") {
          return (
            <div key={key}>
              <span className="font-medium text-muted-foreground capitalize">{displayKey}:</span>
              <pre className="mt-0.5 text-[11px] whitespace-pre-wrap max-h-[150px] overflow-y-auto">
                {JSON.stringify(value, null, 2)}
              </pre>
            </div>
          );
        }

        return (
          <div key={key} className="flex gap-2">
            <span className="font-medium text-muted-foreground capitalize shrink-0">{displayKey}:</span>
            <span>{String(value)}</span>
          </div>
        );
      })}
    </div>
  );
}
