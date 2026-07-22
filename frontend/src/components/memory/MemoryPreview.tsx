import { useCallback, useEffect, useRef, useState } from "react";
import { AppLayout } from "./AppLayout";
import { MOCK_TRACE, QUERY_PRESETS } from "@/data/mockTrace";
import type { TraceState } from "@/types/trace";

const EMPTY: TraceState = {
  ...MOCK_TRACE,
  id: "trace_empty",
  query: "",
  graph: { nodes: [], edges: [] },
  metrics: { ...MOCK_TRACE.metrics, queryTimeSec: 0 },
};

// canned recall built from the mock's real active-path labels so the
// citation pills resolve to actual canvas nodes
function buildAnswer(trace: TraceState): string {
  const path = trace.graph.nodes.filter((n) => n.active).slice(0, 3);
  if (path.length < 2) return "Trace complete — inspect the highlighted path.";
  return (
    `The regression traces back to ${path[0].label}, which propagated through ` +
    `${path[1].label}${path[2] ? ` and surfaced in ${path[2].label}` : ""}. ` +
    `The traced path is highlighted on the canvas.`
  );
}

/**
 * Standalone preview of the memory-tool UI on mock data (route: /memory).
 * Simulates the tracing animation and streams the recall text so every
 * micro-interaction is visible without a running backend.
 */
export function MemoryPreview() {
  const [trace, setTrace] = useState<TraceState>(EMPTY);
  const [tracing, setTracing] = useState(false);
  const [answer, setAnswer] = useState<string | null>(null);
  const [recent, setRecent] = useState<string[]>([]);
  const timers = useRef<number[]>([]);

  useEffect(
    () => () => timers.current.forEach((t) => window.clearTimeout(t)),
    []
  );

  const handleQuery = useCallback((q: string) => {
    timers.current.forEach((t) => window.clearTimeout(t));
    timers.current = [];
    setAnswer(null);
    setTracing(true);
    setRecent((prev) => [q, ...prev.filter((r) => r !== q)].slice(0, 5));

    // graph "search" phase, then reveal the traced path + stream the recall
    const next: TraceState = { ...MOCK_TRACE, id: `trace_${q}`, query: q };
    setTrace({ ...next, graph: MOCK_TRACE.graph });
    timers.current.push(
      window.setTimeout(() => {
        setTracing(false);
        const full = buildAnswer(next);
        let i = 0;
        const tick = () => {
          i += 3;
          setAnswer(full.slice(0, i));
          if (i < full.length) timers.current.push(window.setTimeout(tick, 16));
        };
        tick();
      }, 2200)
    );
  }, []);

  return (
    <AppLayout
      trace={trace}
      tracing={tracing}
      answer={answer}
      suggestions={QUERY_PRESETS.map((p) => ({ label: p.label, query: p.label }))}
      recentQueries={recent}
      onQuery={handleQuery}
    />
  );
}
