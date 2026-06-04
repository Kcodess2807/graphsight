import { memo } from "react";
import {
  EdgeLabelRenderer,
  getBezierPath,
  type EdgeProps,
} from "reactflow";
import { cn } from "@/lib/utils";

export interface TracedEdgeData {
  active: boolean;
  confidence: number;
  relation?: string;
}

function TracedEdgeComponent({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  markerEnd,
}: EdgeProps<TracedEdgeData>) {
  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
    curvature: 0.28,
  });

  const active = data?.active;

  return (
    <>
      {/* soft underlay glow for active edges */}
      {active && (
        <path
          d={path}
          fill="none"
          stroke="url(#trace-gradient)"
          strokeWidth={9}
          strokeOpacity={0.16}
          strokeLinecap="round"
        />
      )}
      <path
        id={id}
        d={path}
        fill="none"
        markerEnd={markerEnd}
        className={cn("react-flow__edge-path", active && "animate-dash-flow")}
        style={{
          stroke: active ? "url(#trace-gradient)" : "hsl(240 6% 82%)",
          strokeWidth: active ? 2.5 : 1.25,
          strokeDasharray: active ? "6 10" : undefined,
          strokeLinecap: "round",
        }}
      />

      {data?.relation && (
        <EdgeLabelRenderer>
          <div
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            }}
            className={cn(
              "pointer-events-none absolute select-none rounded-full border px-1.5 py-0.5 font-mono text-[9px] font-medium tracking-wide",
              active
                ? "border-indigo-100 bg-white text-indigo-600 shadow-soft"
                : "border-transparent bg-zinc-50/80 text-zinc-400"
            )}
          >
            {data.relation}
            {active && (
              <span className="ml-1 text-zinc-400">
                {data.confidence.toFixed(2)}
              </span>
            )}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

export const TracedEdge = memo(TracedEdgeComponent);
