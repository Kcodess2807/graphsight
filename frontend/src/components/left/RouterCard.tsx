import { motion } from "framer-motion";
import { Info, Network, Boxes, Gauge } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { RouterConfidence, RouterWeights } from "@/types/trace";

interface RouterCardProps {
  weights: RouterWeights;
  confidence: RouterConfidence;
}

function WeightBar({
  label,
  symbol,
  value,
  dominant,
  icon: Icon,
}: {
  label: string;
  symbol: string;
  value: number;
  dominant: boolean;
  icon: typeof Network;
}) {
  const pct = Math.round(value * 100);
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <span className="flex items-center gap-1.5 font-medium text-zinc-600">
          <Icon
            className={cn(
              "h-3.5 w-3.5",
              dominant ? "text-indigo-600" : "text-zinc-400"
            )}
          />
          {label}
          <span className="font-mono text-zinc-400">
            ({symbol} = {value.toFixed(2)})
          </span>
        </span>
        <span
          className={cn(
            "font-mono font-semibold tabular-nums",
            dominant ? "text-indigo-700" : "text-zinc-400"
          )}
        >
          {pct}%
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-100">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1], delay: 0.1 }}
          className={cn(
            "h-full rounded-full",
            dominant
              ? "bg-gradient-to-r from-indigo-500 to-indigo-600"
              : "bg-zinc-300"
          )}
        />
      </div>
    </div>
  );
}

export function RouterCard({ weights, confidence }: RouterCardProps) {
  const vectorDominant = weights.vector >= weights.graph;
  const confPct = Math.round(confidence.score * 100);
  const bandPct = Math.round(confidence.uncertainty * 100);
  const isLow = confidence.score < 0.7;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-md bg-indigo-50 text-indigo-600">
              <Network className="h-3.5 w-3.5" />
            </span>
            Hybrid Router
          </CardTitle>
          <Badge variant={weights.intent === "relational" ? "indigo" : "zinc"}>
            {weights.intent} intent
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-3">
          <WeightBar
            label="Vector"
            symbol="α"
            value={weights.vector}
            dominant={vectorDominant}
            icon={Boxes}
          />
          <WeightBar
            label="Graph"
            symbol="β"
            value={weights.graph}
            dominant={!vectorDominant}
            icon={Network}
          />
        </div>

        <Separator />

        {/* Confidence / uncertainty meter */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-xs">
            <span className="flex items-center gap-1.5 font-medium text-zinc-600">
              <Gauge
                className={cn(
                  "h-3.5 w-3.5",
                  isLow ? "text-amber-500" : "text-emerald-600"
                )}
              />
              Router Confidence
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    aria-label="What drives the confidence score?"
                    className="rounded-full text-zinc-300 transition-colors hover:text-zinc-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <Info className="h-3.5 w-3.5" />
                  </button>
                </TooltipTrigger>
                <TooltipContent>{confidence.rationale}</TooltipContent>
              </Tooltip>
            </span>
            <span className="font-mono tabular-nums">
              <span
                className={cn(
                  "font-semibold",
                  isLow ? "text-amber-600" : "text-zinc-900"
                )}
              >
                {confPct}%
              </span>
              <span className="text-zinc-400"> ±{bandPct}%</span>
            </span>
          </div>
          <div className="relative h-2 w-full overflow-hidden rounded-full bg-zinc-100">
            {/* uncertainty band */}
            <div
              className="absolute inset-y-0 rounded-full bg-zinc-200/80"
              style={{
                left: `${Math.max(0, confPct - bandPct)}%`,
                width: `${Math.min(100, confPct + bandPct) - Math.max(0, confPct - bandPct)}%`,
              }}
            />
            {/* confidence fill */}
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${confPct}%` }}
              transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1], delay: 0.2 }}
              className={cn(
                "absolute inset-y-0 left-0 rounded-full",
                isLow
                  ? "bg-gradient-to-r from-amber-400 to-amber-500"
                  : "bg-gradient-to-r from-emerald-500 to-emerald-600"
              )}
            />
          </div>
          <p className="text-[11px] leading-relaxed text-zinc-400">
            {isLow
              ? "Router was uncertain — review the traced path before trusting the answer."
              : "High agreement between arms — the traced path is well-corroborated."}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
