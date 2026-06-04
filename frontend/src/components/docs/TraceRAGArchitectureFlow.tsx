import { useLayoutEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  MessageSquareText,
  Route,
  ScanSearch,
  Spline,
  Combine,
  Cpu,
  FileCheck2,
  Play,
  RotateCcw,
  type LucideIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/* -------------------------------------------------------------------------- */
/*  Architecture model — the lifecycle of a single query                       */
/* -------------------------------------------------------------------------- */

type Accent = "indigo" | "cyan" | "violet" | "purple" | "emerald" | "slate";

interface FlowNodeDef {
  id: string;
  /** The walkthrough step at which this node lights up. */
  step: number;
  title: string;
  subtitle: string;
  icon: LucideIcon;
  accent: Accent;
  /** Center position as a percentage of the canvas. */
  x: number;
  y: number;
}

const NODES: FlowNodeDef[] = [
  { id: "query", step: 0, title: "User Query", subtitle: "Your question, in plain English", icon: MessageSquareText, accent: "slate", x: 50, y: 7 },
  { id: "router", step: 1, title: "Hybrid Router", subtitle: "Decides how much to read vs. trace", icon: Route, accent: "indigo", x: 50, y: 25 },
  { id: "vector", step: 2, title: "Vector Search", subtitle: "The Skimmer · matches meaning", icon: ScanSearch, accent: "indigo", x: 26, y: 47 },
  { id: "graph", step: 2, title: "Graph Traversal", subtitle: "The String Board · follows links", icon: Spline, accent: "cyan", x: 74, y: 47 },
  { id: "fusion", step: 3, title: "Context Fusion", subtitle: "Merges both findings into one set", icon: Combine, accent: "violet", x: 50, y: 67 },
  { id: "groq", step: 4, title: "Groq API · Llama 3", subtitle: "Writes the answer from the evidence", icon: Cpu, accent: "purple", x: 50, y: 83 },
  { id: "final", step: 5, title: "Final Trace & Answer", subtitle: "The answer, with its receipts", icon: FileCheck2, accent: "emerald", x: 50, y: 94 },
];

interface FlowEdge {
  from: string;
  to: string;
  /** Step at which data flows across this edge. */
  step: number;
  accent: Accent;
}

const EDGES: FlowEdge[] = [
  { from: "query", to: "router", step: 1, accent: "indigo" },
  { from: "router", to: "vector", step: 2, accent: "indigo" },
  { from: "router", to: "graph", step: 2, accent: "cyan" },
  { from: "vector", to: "fusion", step: 3, accent: "indigo" },
  { from: "graph", to: "fusion", step: 3, accent: "cyan" },
  { from: "fusion", to: "groq", step: 4, accent: "violet" },
  { from: "groq", to: "final", step: 5, accent: "purple" },
];

const STEP_NAMES = [
  "User Query",
  "Hybrid Router",
  "The Split — Two Brains",
  "Context Fusion",
  "Groq API (Llama 3)",
  "Final Trace & Answer",
];
const TOTAL = STEP_NAMES.length; // 6 steps: 0 → 5

const ACCENT: Record<
  Accent,
  { stroke: string; border: string; glow: string; chip: string; icon: string }
> = {
  indigo: { stroke: "#6366f1", border: "border-indigo-400", glow: "shadow-[0_0_26px_rgba(99,102,241,0.4)]", chip: "bg-indigo-50", icon: "text-indigo-600" },
  cyan: { stroke: "#06b6d4", border: "border-cyan-400", glow: "shadow-[0_0_26px_rgba(6,182,212,0.4)]", chip: "bg-cyan-50", icon: "text-cyan-600" },
  violet: { stroke: "#8b5cf6", border: "border-violet-400", glow: "shadow-[0_0_26px_rgba(139,92,246,0.4)]", chip: "bg-violet-50", icon: "text-violet-600" },
  purple: { stroke: "#a855f7", border: "border-purple-400", glow: "shadow-[0_0_26px_rgba(168,85,247,0.4)]", chip: "bg-purple-50", icon: "text-purple-600" },
  emerald: { stroke: "#10b981", border: "border-emerald-400", glow: "shadow-[0_0_26px_rgba(16,185,129,0.4)]", chip: "bg-emerald-50", icon: "text-emerald-600" },
  slate: { stroke: "#64748b", border: "border-slate-300", glow: "shadow-[0_0_22px_rgba(100,116,139,0.28)]", chip: "bg-slate-100", icon: "text-slate-600" },
};

/* -------------------------------------------------------------------------- */
/*  Component                                                                  */
/* -------------------------------------------------------------------------- */

export function TraceRAGArchitectureFlow() {
  const [activeStep, setActiveStep] = useState(0);
  const canvasRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });

  // Measure the canvas so SVG lines + the data-flow dot use crisp pixel
  // coordinates (keeps the dot perfectly circular and lines aligned on resize).
  useLayoutEffect(() => {
    const el = canvasRef.current;
    if (!el) return;
    const update = () => setSize({ w: el.clientWidth, h: el.clientHeight });
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const px = (id: string) => {
    const n = NODES.find((x) => x.id === id)!;
    return { x: (n.x / 100) * size.w, y: (n.y / 100) * size.h };
  };

  const advance = () => setActiveStep((s) => (s + 1) % TOTAL);
  const restart = () => setActiveStep(0);

  return (
    <div className="not-prose">
      {/* Progress dots + current-step label */}
      <div className="mb-5 flex flex-col items-center gap-3">
        <div className="flex items-center gap-1.5">
          {STEP_NAMES.map((name, i) => (
            <button
              key={name}
              onClick={() => setActiveStep(i)}
              aria-label={`Step ${i + 1}: ${name}`}
              aria-current={i === activeStep}
              className={cn(
                "h-2 rounded-full transition-all duration-300",
                i === activeStep
                  ? "w-7 bg-indigo-600"
                  : i < activeStep
                    ? "w-2 bg-indigo-300"
                    : "w-2 bg-zinc-200 hover:bg-zinc-300"
              )}
            />
          ))}
        </div>
        <p className="text-sm text-zinc-500">
          <span className="font-mono text-zinc-400">
            Step {activeStep + 1}/{TOTAL}
          </span>{" "}
          ·{" "}
          <span className="font-semibold text-zinc-900">
            {STEP_NAMES[activeStep]}
          </span>
        </p>
      </div>

      {/* Canvas */}
      <div
        ref={canvasRef}
        className="relative h-[600px] w-full overflow-hidden rounded-2xl border border-border bg-white shadow-soft sm:h-[680px]"
      >
        <div className="dotted-grid pointer-events-none absolute inset-0 opacity-70" />

        {/* Connecting lines + data-flow dot */}
        <svg className="pointer-events-none absolute inset-0 h-full w-full">
          {size.w > 0 &&
            EDGES.map((e) => {
              const a = px(e.from);
              const b = px(e.to);
              const lit = activeStep >= e.step;
              const flowing = activeStep === e.step;
              const color = ACCENT[e.accent].stroke;
              const travel = {
                cx: [a.x, b.x],
                cy: [a.y, b.y],
              };
              const travelTransition = {
                duration: 1.1,
                ease: "easeInOut" as const,
                repeat: Infinity,
                repeatDelay: 0.15,
              };
              return (
                <g key={`${e.from}-${e.to}`}>
                  <line
                    x1={a.x}
                    y1={a.y}
                    x2={b.x}
                    y2={b.y}
                    stroke={lit ? color : "#e4e4e7"}
                    strokeWidth={lit ? 2.5 : 1.5}
                    strokeLinecap="round"
                    className="transition-all duration-500"
                    style={{ opacity: lit ? 0.95 : 0.7 }}
                  />
                  {flowing && (
                    <>
                      {/* soft halo */}
                      <motion.circle
                        r={11}
                        fill={color}
                        style={{ opacity: 0.22 }}
                        initial={{ cx: a.x, cy: a.y }}
                        animate={travel}
                        transition={travelTransition}
                      />
                      {/* travelling packet */}
                      <motion.circle
                        r={5}
                        fill={color}
                        initial={{ cx: a.x, cy: a.y }}
                        animate={travel}
                        transition={travelTransition}
                      />
                    </>
                  )}
                </g>
              );
            })}
        </svg>

        {/* Nodes */}
        {NODES.map((n) => {
          const active = n.step === activeStep;
          const ac = ACCENT[n.accent];
          const Icon = n.icon;
          return (
            <div
              key={n.id}
              className="absolute z-10 -translate-x-1/2 -translate-y-1/2"
              style={{ left: `${n.x}%`, top: `${n.y}%` }}
            >
              <motion.div
                animate={{ opacity: active ? 1 : 0.4, scale: active ? 1.05 : 1 }}
                transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                className={cn(
                  "w-[150px] rounded-xl border bg-white px-3.5 py-3 text-left transition-shadow duration-500 sm:w-[188px]",
                  active ? cn(ac.border, ac.glow) : "border-border shadow-soft"
                )}
              >
                <div className="flex items-center gap-2.5">
                  <span
                    className={cn(
                      "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-colors duration-500",
                      active ? ac.chip : "bg-zinc-100"
                    )}
                  >
                    <Icon
                      className={cn(
                        "h-4 w-4 transition-colors duration-500",
                        active ? ac.icon : "text-zinc-400"
                      )}
                    />
                  </span>
                  <p className="truncate text-[13px] font-semibold text-zinc-900">
                    {n.title}
                  </p>
                </div>
                <p className="mt-1.5 text-[11px] leading-snug text-zinc-500">
                  {n.subtitle}
                </p>
              </motion.div>
            </div>
          );
        })}

        {/* "The Split" hint label between the two brains */}
        <div
          className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-1/2"
          style={{ left: "50%", top: "47%" }}
        >
          <motion.span
            animate={{ opacity: activeStep === 2 ? 1 : 0.35 }}
            transition={{ duration: 0.4 }}
            className="rounded-full border border-border bg-white px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-400 shadow-soft"
          >
            The Split
          </motion.span>
        </div>
      </div>

      {/* Controls */}
      <div className="mt-6 flex items-center justify-center gap-3">
        <Button onClick={advance} size="lg">
          <Play className="h-4 w-4" />
          Step Through Architecture
        </Button>
        <Button
          onClick={restart}
          variant="outline"
          size="lg"
          aria-label="Restart walkthrough"
        >
          <RotateCcw className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
