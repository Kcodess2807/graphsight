import { TrendingDown, Cpu, Timer, Coins, Boxes } from "lucide-react";
import { Area, AreaChart, ResponsiveContainer } from "recharts";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { NumberTicker } from "@/components/fx/NumberTicker";
import { cn } from "@/lib/utils";
import type { TraceMetrics } from "@/types/trace";

const SPARK = [
  { v: 8 },
  { v: 6.4 },
  { v: 5.1 },
  { v: 4.2 },
  { v: 3.3 },
  { v: 2.8 },
  { v: 2.45 },
];

function StatCard({
  icon: Icon,
  label,
  children,
  tooltip,
  className,
}: {
  icon: typeof Coins;
  label: string;
  children: React.ReactNode;
  tooltip?: string;
  className?: string;
}) {
  const body = (
    <Card
      className={cn(
        "group flex h-full flex-col gap-1.5 p-3.5 transition-shadow hover:shadow-lifted",
        className
      )}
    >
      <div className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-zinc-400">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </div>
      {children}
    </Card>
  );
  if (!tooltip) return body;
  return (
    <Tooltip>
      <TooltipTrigger asChild>{body}</TooltipTrigger>
      <TooltipContent>{tooltip}</TooltipContent>
    </Tooltip>
  );
}

export function MetricsFooter({ metrics }: { metrics: TraceMetrics }) {
  const hasTokens =
    !!metrics.tokens && metrics.tokens.budget > 0 && metrics.tokens.used > 0;
  const hasRam = metrics.peakRamGb != null && metrics.peakRamGb > 0;
  const hasNodes = metrics.nodesEvaluated != null;

  // a lone secondary card spans full width to avoid a ragged half-card
  const secondary: React.ReactNode[] = [];
  if (hasTokens && hasNodes) {
    secondary.push(
      <StatCard
        key="nodes"
        icon={Boxes}
        label="Nodes Evaluated"
        tooltip="Entities the router scored while assembling context (trace_log.metrics)."
      >
        <div className="font-mono text-xl font-semibold tracking-tight text-zinc-900">
          <NumberTicker value={metrics.nodesEvaluated!} group />
        </div>
      </StatCard>
    );
  }
  if (hasRam) {
    secondary.push(
      <StatCard
        key="ram"
        icon={Cpu}
        label="Peak RAM"
        tooltip="Peak resident memory — runs comfortably on a laptop, no server."
      >
        <div className="font-mono text-xl font-semibold tracking-tight text-zinc-900">
          <NumberTicker value={metrics.peakRamGb!} decimals={1} suffix=" GB" />
        </div>
      </StatCard>
    );
  }
  secondary.push(
    <StatCard
      key="time"
      icon={Timer}
      label="Query Time"
      tooltip="End-to-end latency: trace + sub-graph fetch (measured round-trip)."
    >
      <div className="font-mono text-xl font-semibold tracking-tight text-zinc-900">
        <NumberTicker value={metrics.queryTimeSec} decimals={2} suffix="s" />
      </div>
    </StatCard>
  );
  const secondarySpan = secondary.length === 1 ? "col-span-2" : "";

  return (
    <div className="grid grid-cols-2 gap-3">
      {hasTokens ? (
        <StatCard
          icon={Coins}
          label="Token Footprint"
          className="col-span-2"
          tooltip="Tokens sent to the LLM vs. the model's context budget. Lower is cheaper and faster."
        >
          <div className="flex items-end justify-between gap-3">
            <div>
              <div className="flex items-baseline gap-1 font-mono text-2xl font-semibold tracking-tight text-zinc-900">
                <NumberTicker value={metrics.tokens!.used} group />
                <span className="text-sm font-normal text-zinc-400">
                  / {metrics.tokens!.budget.toLocaleString()}
                </span>
              </div>
              <Badge variant="emerald" className="mt-1.5 gap-1">
                <TrendingDown className="h-3 w-3" />
                <NumberTicker
                  value={metrics.tokens!.reductionPct}
                  suffix="% reduction"
                />
              </Badge>
            </div>
            <div className="h-12 w-28 shrink-0 opacity-90">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart
                  data={SPARK}
                  margin={{ top: 4, bottom: 0, left: 0, right: 0 }}
                >
                  <defs>
                    <linearGradient id="spark" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#10b981" stopOpacity={0.35} />
                      <stop offset="100%" stopColor="#10b981" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <Area
                    type="monotone"
                    dataKey="v"
                    stroke="#10b981"
                    strokeWidth={2}
                    fill="url(#spark)"
                    isAnimationActive
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        </StatCard>
      ) : (
        // no token telemetry, so nodes evaluated becomes the hero
        <StatCard
          icon={Boxes}
          label="Nodes Evaluated"
          className="col-span-2"
          tooltip="Entities the router scored while assembling context (trace_log.metrics)."
        >
          <div className="flex items-baseline gap-2 font-mono text-2xl font-semibold tracking-tight text-zinc-900">
            <NumberTicker value={metrics.nodesEvaluated ?? 0} group />
            <span className="text-sm font-normal text-zinc-400">
              entities scored
            </span>
          </div>
        </StatCard>
      )}

      {secondary.map((card) => (
        <div key={(card as React.ReactElement).key} className={secondarySpan}>
          {card}
        </div>
      ))}
    </div>
  );
}
