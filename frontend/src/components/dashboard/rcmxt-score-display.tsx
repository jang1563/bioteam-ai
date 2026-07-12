"use client";

import { useState } from "react";
import type { RCMXTScore } from "@/types/api";

const RCMXT_AXES = [
  { key: "R" as const, label: "R", full: "Reproducibility" },
  { key: "C" as const, label: "C", full: "Condition" },
  { key: "M" as const, label: "M", full: "Methodology" },
  { key: "X" as const, label: "X", full: "Cross-Omics" },
  { key: "T" as const, label: "T", full: "Temporal" },
];

export const RADAR_COLORS = [
  { stroke: "rgb(20, 184, 166)", fill: "rgba(20, 184, 166, 0.15)" },   // teal
  { stroke: "rgb(245, 158, 11)", fill: "rgba(245, 158, 11, 0.15)" },   // amber
  { stroke: "rgb(139, 92, 246)", fill: "rgba(139, 92, 246, 0.15)" },   // violet
  { stroke: "rgb(16, 185, 129)", fill: "rgba(16, 185, 129, 0.15)" },   // emerald
  { stroke: "rgb(244, 63, 94)", fill: "rgba(244, 63, 94, 0.15)" },     // rose
];

function RCMXTRadarChart({ scores }: { scores: RCMXTScore[] }) {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);
  const size = 220;
  const cx = size / 2;
  const cy = size / 2;
  const radius = 85;
  const rings = [0.25, 0.5, 0.75, 1.0];
  const n = RCMXT_AXES.length;

  const getPoint = (axisIdx: number, value: number) => {
    const angle = -Math.PI / 2 + (2 * Math.PI * axisIdx) / n;
    const d = value * radius;
    return { x: cx + d * Math.cos(angle), y: cy + d * Math.sin(angle) };
  };

  const getPolygonPoints = (score: RCMXTScore) =>
    RCMXT_AXES.map((axis, i) => {
      const val = score[axis.key];
      const v = val !== null && val !== undefined ? Math.max(0, Math.min(1, val)) : 0;
      const pt = getPoint(i, v);
      return `${pt.x},${pt.y}`;
    }).join(" ");

  return (
    <div className="flex flex-col items-center">
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="select-none"
        role="img"
        aria-label="RCMXT radar chart showing evidence quality scores"
      >
        {/* Grid rings */}
        {rings.map((ring) => (
          <polygon
            key={ring}
            points={Array.from({ length: n }, (_, i) => {
              const pt = getPoint(i, ring);
              return `${pt.x},${pt.y}`;
            }).join(" ")}
            fill="none"
            stroke="currentColor"
            strokeWidth={ring === 1 ? 0.8 : 0.4}
            className="text-border"
            strokeDasharray={ring < 1 ? "2,2" : "none"}
          />
        ))}

        {/* Axis lines */}
        {RCMXT_AXES.map((_, i) => {
          const pt = getPoint(i, 1);
          return (
            <line
              key={i}
              x1={cx}
              y1={cy}
              x2={pt.x}
              y2={pt.y}
              stroke="currentColor"
              strokeWidth={0.4}
              className="text-border"
            />
          );
        })}

        {/* Data polygons */}
        {scores.map((score, idx) => {
          const color = RADAR_COLORS[idx % RADAR_COLORS.length];
          const isHovered = hoveredIdx === idx;
          const isOther = hoveredIdx !== null && hoveredIdx !== idx;
          return (
            <polygon
              key={idx}
              points={getPolygonPoints(score)}
              fill={color.fill}
              stroke={color.stroke}
              strokeWidth={isHovered ? 2 : 1.2}
              opacity={isOther ? 0.2 : 1}
              className="transition-opacity duration-200"
              onMouseEnter={() => setHoveredIdx(idx)}
              onMouseLeave={() => setHoveredIdx(null)}
              style={{ cursor: "pointer" }}
            />
          );
        })}

        {/* Data points */}
        {scores.map((score, idx) => {
          const color = RADAR_COLORS[idx % RADAR_COLORS.length];
          const isOther = hoveredIdx !== null && hoveredIdx !== idx;
          return RCMXT_AXES.map((axis, i) => {
            const val = score[axis.key];
            const v = val !== null && val !== undefined ? Math.max(0, Math.min(1, val)) : 0;
            if (v === 0) return null;
            const pt = getPoint(i, v);
            return (
              <circle
                key={`${idx}-${i}`}
                cx={pt.x}
                cy={pt.y}
                r={isOther ? 1.5 : 2.5}
                fill={color.stroke}
                opacity={isOther ? 0.2 : 1}
                className="transition-opacity duration-200"
              />
            );
          });
        })}

        {/* Axis labels */}
        {RCMXT_AXES.map((axis, i) => {
          const pt = getPoint(i, 1.18);
          return (
            <text
              key={i}
              x={pt.x}
              y={pt.y}
              textAnchor="middle"
              dominantBaseline="central"
              className="fill-muted-foreground text-[10px] font-medium"
            >
              {axis.label}
            </text>
          );
        })}

        {/* Ring value labels */}
        {rings.map((ring) => {
          const pt = getPoint(0, ring);
          return (
            <text
              key={ring}
              x={pt.x + 8}
              y={pt.y}
              className="fill-muted-foreground text-[8px]"
              textAnchor="start"
              dominantBaseline="central"
            >
              {ring.toFixed(2)}
            </text>
          );
        })}
      </svg>

      {/* Legend */}
      {scores.length > 1 && (
        <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1 justify-center">
          {scores.map((score, idx) => {
            const color = RADAR_COLORS[idx % RADAR_COLORS.length];
            return (
              <button
                key={idx}
                className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground transition-colors"
                onMouseEnter={() => setHoveredIdx(idx)}
                onMouseLeave={() => setHoveredIdx(null)}
              >
                <span
                  className="inline-block w-2 h-2 rounded-full shrink-0"
                  style={{ backgroundColor: color.stroke }}
                />
                <span className="truncate max-w-[120px]">{score.claim}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function RCMXTScoreTable({ scores }: { scores: RCMXTScore[] }) {
  return (
    <div>
      <p className="mb-1.5 text-xs font-medium text-muted-foreground">
        Evidence Quality (RCMXT)
      </p>

      {/* Radar Chart */}
      <RCMXTRadarChart scores={scores} />

      <div className="mt-3" />
      <div className="overflow-x-auto rounded border border-border">
        <table className="w-full text-[11px]">
          <thead>
            <tr className="border-b border-border bg-accent/50">
              <th className="px-2 py-1 text-left font-medium text-muted-foreground">Claim</th>
              <th className="px-1.5 py-1 text-center font-medium text-muted-foreground" title="Reproducibility">R</th>
              <th className="px-1.5 py-1 text-center font-medium text-muted-foreground" title="Condition Specificity">C</th>
              <th className="px-1.5 py-1 text-center font-medium text-muted-foreground" title="Methodology">M</th>
              <th className="px-1.5 py-1 text-center font-medium text-muted-foreground" title="Cross-Omics">X</th>
              <th className="px-1.5 py-1 text-center font-medium text-muted-foreground" title="Temporal">T</th>
              <th className="px-1.5 py-1 text-center font-medium text-muted-foreground">Score</th>
            </tr>
          </thead>
          <tbody>
            {scores.map((s, i) => (
              <tr key={i} className="border-b border-border last:border-0">
                <td className="px-2 py-1 max-w-[180px] truncate" title={s.claim}>
                  <span className="flex items-center gap-1.5">
                    <span
                      className="inline-block w-1.5 h-1.5 rounded-full shrink-0"
                      style={{ backgroundColor: RADAR_COLORS[i % RADAR_COLORS.length].stroke }}
                    />
                    {s.claim}
                  </span>
                </td>
                <td className="px-1.5 py-1 text-center font-mono">{s.R.toFixed(2)}</td>
                <td className="px-1.5 py-1 text-center font-mono">{s.C.toFixed(2)}</td>
                <td className="px-1.5 py-1 text-center font-mono">{s.M.toFixed(2)}</td>
                <td className="px-1.5 py-1 text-center font-mono text-muted-foreground">
                  {s.X !== null ? s.X.toFixed(2) : "\u2014"}
                </td>
                <td className="px-1.5 py-1 text-center font-mono">{s.T.toFixed(2)}</td>
                <td className="px-1.5 py-1 text-center font-mono font-medium">
                  {s.composite !== null ? s.composite.toFixed(2) : "\u2014"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-1 text-[10px] text-muted-foreground">
        v0.1-heuristic | R=Reproducibility C=Condition M=Methodology X=Cross-Omics T=Temporal
      </p>
    </div>
  );
}
