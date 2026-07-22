import { memo } from "react";
import { Handle, Position, type NodeProps } from "reactflow";
import { motion } from "framer-motion";
import { MEMORY_ENTITY_STYLES } from "./entityTheme";
import { cn } from "@/lib/utils";
import type { TraceNode } from "@/types/trace";

export interface MemoryNodeData extends TraceNode {
  // true while a query is running — drives the staggered sonar ring
  searching?: boolean;
  // index into the node list, used only to stagger the searching animation
  searchDelayIndex?: number;
}

// w-[240px] is coupled to NODE_HALF_W in GraphCanvas.tsx — keep them in sync
function MemoryNodeComponent({ data, selected }: NodeProps<MemoryNodeData>) {
  const style = MEMORY_ENTITY_STYLES[data.type];
  const Icon = style.icon;
  const lit = data.active || selected;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: lit ? 1 : 0.55, scale: selected ? 1.05 : 1 }}
      whileHover={{ opacity: 1, scale: 1.03 }}
      transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
      className={cn(
        "group relative flex w-[240px] items-center gap-3 rounded-xl border bg-white px-3.5 py-2.5",
        "transition-shadow duration-300",
        data.active
          ? "border-[#131316] shadow-[3px_4px_0_0_#059669]"
          : "border-zinc-300 shadow-[2px_3px_0_0_rgba(19,19,22,0.12)] hover:border-[#131316]",
        // citation focus: lime hard shadow, the landing's highlight color
        selected && "z-10 border-[#131316] shadow-[3px_4px_0_0_#C8F169]"
      )}
    >
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />

      {/* sonar ring while the graph algorithm is "visiting" nodes */}
      {data.searching && (
        <span
          className="pointer-events-none absolute inset-0 rounded-xl border-2 border-emerald-500/60 animate-trace-ping"
          style={{ animationDelay: `${(data.searchDelayIndex ?? 0) % 6 * 0.22}s` }}
        />
      )}

      <span
        className={cn(
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border",
          style.well
        )}
      >
        <Icon className={cn("h-4 w-4", style.glyph)} strokeWidth={2.25} />
      </span>

      <div className="min-w-0 flex-1">
        <p
          className={cn(
            "truncate text-[13px] font-bold leading-tight",
            lit ? "text-[#131316]" : "text-zinc-500"
          )}
        >
          {data.label}
        </p>
        <p className="truncate font-mono text-[9.5px] uppercase tracking-[0.15em] text-zinc-400">
          {style.label}
        </p>
      </div>

      {data.active && data.score != null && (
        <span
          className="shrink-0 rounded-full border border-[#131316] px-2 py-0.5 font-mono text-[10px] font-bold text-[#131316]"
          style={{ backgroundColor: "#C8F169" }}
        >
          {data.score.toFixed(2)}
        </span>
      )}
    </motion.div>
  );
}

export const MemoryNode = memo(MemoryNodeComponent);
