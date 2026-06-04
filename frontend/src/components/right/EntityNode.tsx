import { memo } from "react";
import { Handle, Position, type NodeProps } from "reactflow";
import { motion } from "framer-motion";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ENTITY_STYLES } from "@/lib/entity";
import { cn } from "@/lib/utils";
import type { TraceNode } from "@/types/trace";

export type EntityNodeData = TraceNode;

function EntityNodeComponent({ data }: NodeProps<EntityNodeData>) {
  const style = ENTITY_STYLES[data.type];
  const Icon = style.icon;
  const active = data.active;

  return (
    <HoverCard openDelay={120} closeDelay={60}>
      <HoverCardTrigger asChild>
        <motion.div
          initial={{ opacity: 0, scale: 0.92 }}
          animate={{ opacity: active ? 1 : 0.4, scale: 1 }}
          whileHover={{ scale: 1.04, opacity: 1 }}
          transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
          className={cn(
            "group relative flex w-[164px] items-center gap-2.5 rounded-xl border px-3 py-2.5 transition-shadow",
            active
              ? // Active / traced — pops forward off the canvas (indigo system)
                "border-transparent bg-white shadow-node ring-2 ring-indigo-500"
              : // Dimmed background context — quiet grey, recedes
                "border-zinc-200 bg-white/80 shadow-soft grayscale-[0.35]"
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
                "truncate text-[13px] font-semibold leading-tight",
                active ? "text-zinc-900" : "text-zinc-500"
              )}
            >
              {data.label}
            </p>
            <p className="truncate text-[10px] font-medium uppercase tracking-wide text-zinc-400">
              {style.label}
            </p>
          </div>

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
            {data.similarity != null && (
              <Badge variant="zinc" className="font-mono">
                sim {data.similarity.toFixed(2)}
              </Badge>
            )}
          </div>

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

          {data.meta?.snippet && (
            <p className="rounded-lg bg-zinc-50 p-2 text-[11px] leading-relaxed text-zinc-600">
              {data.meta.snippet}
            </p>
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
