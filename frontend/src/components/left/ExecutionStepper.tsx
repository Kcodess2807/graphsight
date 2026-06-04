import { motion } from "framer-motion";
import { Check, Loader2, Boxes, Network, Layers } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { ExecutionStep } from "@/types/trace";

const STEP_ICON = {
  vector: Boxes,
  graph: Network,
  default: Layers,
} as const;

function StepNode({ step, isLast }: { step: ExecutionStep; isLast: boolean }) {
  const Icon =
    step.arm === "vector"
      ? STEP_ICON.vector
      : step.arm === "graph"
        ? STEP_ICON.graph
        : STEP_ICON.default;
  const done = step.status === "complete";
  const active = step.status === "active";

  return (
    <motion.li
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: step.index * 0.12, ease: "easeOut" }}
      className="relative flex gap-3.5 pb-5 last:pb-0"
    >
      {/* connector line */}
      {!isLast && (
        <span
          aria-hidden
          className={cn(
            "absolute left-[15px] top-8 h-[calc(100%-1.5rem)] w-px",
            done ? "bg-indigo-200" : "bg-zinc-200"
          )}
        />
      )}

      {/* status marker */}
      <span
        className={cn(
          "relative z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border transition-colors",
          done && "border-indigo-200 bg-indigo-50 text-indigo-600",
          active && "border-indigo-500 bg-white text-indigo-600 ring-4 ring-indigo-500/15",
          step.status === "pending" && "border-zinc-200 bg-white text-zinc-300"
        )}
      >
        {done ? (
          <Check className="h-4 w-4" strokeWidth={3} />
        ) : active ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Icon className="h-4 w-4" />
        )}
      </span>

      <div className="flex-1 pt-0.5">
        <div className="flex items-center justify-between gap-2">
          <p
            className={cn(
              "text-sm font-semibold",
              step.status === "pending" ? "text-zinc-400" : "text-zinc-900"
            )}
          >
            <span className="font-mono text-xs text-zinc-400">
              {step.index}.
            </span>{" "}
            {step.title}
          </p>
          {step.badge && (
            <Badge
              variant={step.arm === "graph" ? "indigo" : "zinc"}
              className="shrink-0 font-mono"
            >
              {step.badge}
            </Badge>
          )}
        </div>
        <p
          className={cn(
            "mt-0.5 text-xs leading-relaxed",
            step.status === "pending" ? "text-zinc-300" : "text-zinc-500"
          )}
        >
          {step.detail}
        </p>
        {step.durationMs != null && step.status !== "pending" && (
          <p className="mt-1 font-mono text-[10px] text-zinc-400">
            {step.durationMs} ms
          </p>
        )}
      </div>
    </motion.li>
  );
}

export function ExecutionStepper({ steps }: { steps: ExecutionStep[] }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-md bg-indigo-50 text-indigo-600">
            <Layers className="h-3.5 w-3.5" />
          </span>
          Execution Plan
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ol className="mt-1">
          {steps.map((step, i) => (
            <StepNode
              key={step.id}
              step={step}
              isLast={i === steps.length - 1}
            />
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}
