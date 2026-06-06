import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Check, Loader2, Boxes, Network, Layers, Compass, Sparkles } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * Live pipeline ticker shown WHILE a query runs (replaces the dead skeleton).
 *
 * /api/trace is a single blocking request, so we can't get true per-phase
 * callbacks — but the phases below ARE the real router pipeline, advanced on a
 * timer roughly calibrated to typical latency. The point is honest motion that
 * maps to what the backend is doing, so the wait feels like progress instead of
 * a spinner. The last phase ("Generating answer") holds until loading ends.
 */
const PHASES = [
  { label: "Classifying intent", icon: Compass },
  { label: "Searching vectors", icon: Boxes },
  { label: "Traversing graph", icon: Network },
  { label: "Assembling context", icon: Layers },
  { label: "Generating answer", icon: Sparkles },
] as const;

// How long (ms) to dwell on each phase before advancing. The final phase is
// sticky (we never auto-complete it — only the real response does).
const PHASE_MS = 650;

export function LiveProgress() {
  const [current, setCurrent] = useState(0);

  useEffect(() => {
    const t = setInterval(() => {
      // Advance up to — but not past — the final phase; it holds until unmount.
      setCurrent((c) => Math.min(c + 1, PHASES.length - 1));
    }, PHASE_MS);
    return () => clearInterval(t);
  }, []);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-md bg-indigo-50 text-indigo-600">
            <Layers className="h-3.5 w-3.5" />
          </span>
          Tracing…
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ol className="mt-1">
          {PHASES.map((phase, i) => {
            const done = i < current;
            const active = i === current;
            const Icon = phase.icon;
            const isLast = i === PHASES.length - 1;
            return (
              <li
                key={phase.label}
                className="relative flex gap-3.5 pb-5 last:pb-0"
              >
                {!isLast && (
                  <span
                    aria-hidden
                    className={cn(
                      "absolute left-[15px] top-8 h-[calc(100%-1.5rem)] w-px",
                      done ? "bg-indigo-200" : "bg-zinc-200"
                    )}
                  />
                )}
                <span
                  className={cn(
                    "relative z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border transition-colors",
                    done && "border-indigo-200 bg-indigo-50 text-indigo-600",
                    active &&
                      "border-indigo-500 bg-white text-indigo-600 ring-4 ring-indigo-500/15",
                    !done && !active && "border-zinc-200 bg-white text-zinc-300"
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
                <div className="flex-1 pt-1">
                  <motion.p
                    initial={false}
                    animate={{ opacity: done || active ? 1 : 0.5 }}
                    className={cn(
                      "text-sm font-medium",
                      active ? "text-zinc-900" : "text-zinc-500"
                    )}
                  >
                    {phase.label}
                  </motion.p>
                </div>
              </li>
            );
          })}
        </ol>
      </CardContent>
    </Card>
  );
}
