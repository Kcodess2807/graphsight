import { memo, useCallback, useState } from "react";
import { Handle, Position, type NodeProps } from "reactflow";
import { motion } from "framer-motion";
import { ExternalLink, Sparkles } from "lucide-react";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ENTITY_STYLES } from "@/lib/entity";
import { summarizeNode } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { TraceNode } from "@/types/trace";

export type EntityNodeData = TraceNode;

function EntityNodeComponent({ data, selected }: NodeProps<EntityNodeData>) {
  const style = ENTITY_STYLES[data.type];
  const Icon = style.icon;
  const active = data.active;
  const snippet = data.meta?.snippet;

  // Lazy LLM summary: fetched only when the hover card opens (server-cached).
  const [summary, setSummary] = useState<string | null>(null);
  const [summarizing, setSummarizing] = useState(false);
  const handleOpenChange = useCallback(
    (open: boolean) => {
      if (!open || summary !== null || summarizing || !snippet) return;
      setSummarizing(true);
      summarizeNode(data.id, snippet)
        .then((s) => setSummary(s))
        .catch(() => setSummary(""))
        .finally(() => setSummarizing(false));
    },
    [data.id, snippet, summary, summarizing]
  );

  return (
    <HoverCard openDelay={120} closeDelay={60} onOpenChange={handleOpenChange}>
      <HoverCardTrigger asChild>
        <motion.div
          initial={{ opacity: 0, scale: 0.92 }}
          // When focused via an answer citation, force full opacity + a slight
          // pop even if the node is an inactive/background one, so it can't hide.
          animate={{ opacity: active || selected ? 1 : 0.4, scale: selected ? 1.06 : 1 }}
          whileHover={{ scale: 1.04, opacity: 1 }}
          transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
          className={cn(
            // GRAPH-LEGIBILITY PASS — card widened 164px -> 220px so full entity
            // labels (e.g. "oliver-newhouse-jones") fit instead of clipping to
            // "oli...". CRITICAL: this width is COUPLED to NODE_W in lib/layout.ts
            // (dagre needs the width up front to space ranks). If you change the
            // px here, change NODE_W there too, or nodes will overlap / gap.
            "group relative flex w-[220px] items-center gap-2.5 rounded-xl border px-3 py-2.5 transition-shadow",
            active
              ? // Active / traced — pops forward off the canvas (indigo system)
                "border-transparent bg-white shadow-node ring-2 ring-indigo-500"
              : // Dimmed background context — quiet grey, recedes
                "border-zinc-200 bg-white/80 shadow-soft grayscale-[0.35]",
            // Citation focus ring (amber) — overrides the dimmed look so a
            // clicked citation is unmistakable, layered above the active ring.
            selected && "z-10 grayscale-0 ring-2 ring-amber-400 ring-offset-2"
          )}
        >
          {/* invisible handles so edges anchor cleanly */}
          <Handle type="target" position={Position.Left} />
          <Handle type="source" position={Position.Right} />

          <span
            className={cn(
              "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border",
              style.chip
            )}
          >
            <Icon className={cn("h-4 w-4", style.iconColor)} />
          </span>
          <div className="min-w-0 flex-1">
            <p
              className={cn(
                // Was `truncate` (1 line + ellipsis) — the source of "oli...".
                // Now `line-clamp-2` lets the label wrap to TWO lines and only
                // ellipsizes if it overflows even that, so normal names show in
                // full. `break-words` lets long unbroken tokens (slugs, urls)
                // wrap mid-word instead of forcing the card wider than NODE_W.
                "line-clamp-2 break-words text-[13px] font-semibold leading-tight",
                active ? "text-zinc-900" : "text-zinc-500"
              )}
            >
              {data.label}
            </p>
            <p className="truncate text-[10px] font-medium uppercase tracking-wide text-zinc-400">
              {style.label}
            </p>
          </div>

          {active && data.score != null && (
            <span className="shrink-0 rounded-md bg-indigo-50 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-indigo-600">
              {data.score.toFixed(2)}
            </span>
          )}

          {active && (
            <motion.span
              layoutId={`pulse-${data.id}`}
              className="absolute -right-1 -top-1 flex h-3 w-3"
            >
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-indigo-400 opacity-60" />
              <span className="relative inline-flex h-3 w-3 rounded-full bg-indigo-500 ring-2 ring-white" />
            </motion.span>
          )}
        </motion.div>
      </HoverCardTrigger>

      <HoverCardContent side="top" align="start">
        <div className="space-y-2.5">
          <div className="flex items-start gap-2.5">
            <span
              className={cn(
                "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border",
                style.chip
              )}
            >
              <Icon className={cn("h-4.5 w-4.5", style.iconColor)} />
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-zinc-900">
                {data.label}
              </p>
              {data.meta?.subtitle && (
                <p className="text-xs text-zinc-500">{data.meta.subtitle}</p>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            <Badge variant={style.badge}>{style.label}</Badge>
            {active && <Badge variant="indigo">on traced path</Badge>}
            {data.orphan && <Badge variant="muted">orphan</Badge>}
          </div>

          {(data.score != null ||
            data.similarity != null ||
            (data.meta?.scoreGraph ?? 0) > 0 ||
            data.meta?.connections != null) && (
            <>
              <Separator />
              <dl className="space-y-1 text-xs">
                {data.score != null && (
                  <Row label="Score (fused)" value={data.score.toFixed(3)} mono />
                )}
                {data.similarity != null && (
                  <Row label="Vector sim" value={data.similarity.toFixed(3)} mono />
                )}
                {(data.meta?.scoreGraph ?? 0) > 0 && (
                  <Row
                    label="Graph score"
                    value={data.meta!.scoreGraph!.toFixed(3)}
                    mono
                  />
                )}
                {data.meta?.connections != null && (
                  <Row
                    label="Connections"
                    value={String(data.meta.connections)}
                    mono
                  />
                )}
              </dl>
            </>
          )}

          {(data.meta?.owner || data.meta?.status || data.meta?.timestamp) && (
            <>
              <Separator />
              <dl className="space-y-1 text-xs">
                {data.meta?.owner && (
                  <Row label="Owner" value={data.meta.owner} />
                )}
                {data.meta?.status && (
                  <Row label="Status" value={data.meta.status} />
                )}
                {data.meta?.timestamp && (
                  <Row label="When" value={data.meta.timestamp} mono />
                )}
              </dl>
            </>
          )}

          {data.meta?.sourceUrl && (
            <a
              href={data.meta.sourceUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-[11px] font-medium text-indigo-600 hover:text-indigo-700"
            >
              <ExternalLink className="h-3 w-3" /> View source
            </a>
          )}

          {snippet && (
            <div className="rounded-lg bg-zinc-50 p-2">
              {summarizing ? (
                <p className="text-[11px] italic text-zinc-400">Summarizing…</p>
              ) : summary ? (
                <>
                  <p className="mb-1 flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-indigo-500">
                    <Sparkles className="h-2.5 w-2.5" /> Summary
                  </p>
                  <p className="text-[11px] leading-relaxed text-zinc-700">
                    {summary}
                  </p>
                </>
              ) : (
                <p className="text-[11px] leading-relaxed text-zinc-600">
                  {snippet}
                </p>
              )}
            </div>
          )}
        </div>
      </HoverCardContent>
    </HoverCard>
  );
}

function Row({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-zinc-400">{label}</dt>
      <dd
        className={cn(
          "truncate text-right font-medium text-zinc-700",
          mono && "font-mono text-[11px]"
        )}
      >
        {value}
      </dd>
    </div>
  );
}

export const EntityNode = memo(EntityNodeComponent);
