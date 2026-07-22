import { motion, AnimatePresence } from "framer-motion";
import { Crosshair, ExternalLink, X } from "lucide-react";
import { MEMORY_ENTITY_STYLES } from "./entityTheme";
import { cn } from "@/lib/utils";
import type { TraceNode } from "@/types/trace";

interface InspectorPanelProps {
  node: TraceNode | null;
  onClose: () => void;
  // re-centers the canvas camera on this node
  onCenter: (id: string) => void;
}

/**
 * Floating glass inspector. Positioned absolutely over the canvas (right edge)
 * so the graph stays visible through the blur — mount it inside the canvas
 * area's relative container, after GraphCanvas.
 */
export function InspectorPanel({ node, onClose, onCenter }: InspectorPanelProps) {
  return (
    <AnimatePresence>
      {node && <InspectorContent key={node.id} node={node} onClose={onClose} onCenter={onCenter} />}
    </AnimatePresence>
  );
}

function InspectorContent({
  node,
  onClose,
  onCenter,
}: {
  node: TraceNode;
  onClose: () => void;
  onCenter: (id: string) => void;
}) {
  const style = MEMORY_ENTITY_STYLES[node.type];
  const Icon = style.icon;

  return (
    <motion.aside
      initial={{ x: 40, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: 40, opacity: 0 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      className={cn(
        "absolute inset-y-4 right-4 z-30 flex w-[380px] max-w-[calc(100%-2rem)] flex-col",
        "rounded-2xl border border-[#131316] bg-white shadow-[6px_7px_0_0_#131316]"
      )}
    >
      {/* header */}
      <div className="flex items-start gap-3 border-b border-[#131316] p-4">
        <span
          className={cn(
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border",
            style.well
          )}
        >
          <Icon className={cn("h-4.5 w-4.5", style.glyph)} />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-sm font-bold text-[#131316]">
            {node.label}
          </h2>
          <p className="mt-0.5 font-mono text-[10px] uppercase tracking-widest text-zinc-400">
            {style.label} · <span className="normal-case">{node.id}</span>
          </p>
        </div>
        <div className="flex shrink-0 gap-1">
          <IconButton label="Center in graph" onClick={() => onCenter(node.id)}>
            <Crosshair className="h-3.5 w-3.5" />
          </IconButton>
          <IconButton label="Close inspector" onClick={onClose}>
            <X className="h-3.5 w-3.5" />
          </IconButton>
        </div>
      </div>

      {/* body */}
      <div className="scrollbar-thin min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        {node.meta?.subtitle && (
          <p className="text-[13px] leading-relaxed text-zinc-700">
            {node.meta.subtitle}
          </p>
        )}

        {/* retrieval scores */}
        {(node.score != null || node.similarity != null) && (
          <section>
            <InspectorLabel>Retrieval</InspectorLabel>
            <dl className="mt-2 space-y-1.5">
              {node.score != null && (
                <MetaRow label="Fused score" value={node.score.toFixed(3)} accent />
              )}
              {node.similarity != null && (
                <MetaRow label="Vector similarity" value={node.similarity.toFixed(3)} />
              )}
              {(node.meta?.scoreGraph ?? 0) > 0 && (
                <MetaRow label="Graph score" value={node.meta!.scoreGraph!.toFixed(3)} />
              )}
              {node.meta?.connections != null && (
                <MetaRow label="Connections" value={String(node.meta.connections)} />
              )}
            </dl>
          </section>
        )}

        {/* exact context handed to the LLM — hyper-transparency is the point */}
        {node.meta?.snippet && (
          <section>
            <InspectorLabel>Context</InspectorLabel>
            <pre
              className={cn(
                "mt-2 overflow-x-auto whitespace-pre-wrap rounded-xl border border-zinc-200",
                "bg-[#FAFAFB] p-3 font-mono text-[11px] leading-relaxed text-zinc-700"
              )}
            >
              {node.meta.snippet}
            </pre>
          </section>
        )}

        {/* provenance */}
        {(node.meta?.owner || node.meta?.status || node.meta?.timestamp) && (
          <section>
            <InspectorLabel>Provenance</InspectorLabel>
            <dl className="mt-2 space-y-1.5">
              {node.meta?.owner && <MetaRow label="Owner" value={node.meta.owner} />}
              {node.meta?.status && <MetaRow label="Status" value={node.meta.status} />}
              {node.meta?.timestamp && (
                <MetaRow label="When" value={node.meta.timestamp} />
              )}
            </dl>
          </section>
        )}
      </div>

      {/* footer */}
      {node.meta?.sourceUrl && (
        <div className="border-t border-[#131316] p-3">
          <a
            href={node.meta.sourceUrl}
            target="_blank"
            rel="noreferrer"
            className={cn(
              "flex items-center justify-center gap-1.5 rounded-lg border border-[#131316] bg-white shadow-[2px_3px_0_0_#131316]",
              "py-2 text-xs font-bold text-[#131316] transition-transform duration-150",
              "hover:-translate-y-0.5"
            )}
          >
            <ExternalLink className="h-3.5 w-3.5" /> Open source
          </a>
        </div>
      )}
    </motion.aside>
  );
}

function InspectorLabel({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="font-mono text-[10px] font-medium uppercase tracking-[0.2em] text-zinc-400">
      {children}
    </h3>
  );
}

function MetaRow({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3 text-xs">
      <dt className="text-zinc-400">{label}</dt>
      <dd
        className={cn(
          "truncate text-right font-mono text-[11px]",
          accent ? "font-bold text-emerald-600" : "text-zinc-700"
        )}
      >
        {value}
      </dd>
    </div>
  );
}

function IconButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className={cn(
        "flex h-7 w-7 items-center justify-center rounded-lg text-zinc-500",
        "transition-colors hover:bg-zinc-100 hover:text-[#131316]"
      )}
    >
      {children}
    </button>
  );
}
