import { useCallback, useEffect, useState } from "react";
import { PanelLeft, Network } from "lucide-react";
import { toast } from "sonner";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { LeftPane } from "@/components/left/LeftPane";
import { VisualTracer } from "@/components/right/VisualTracer";
import { MOCK_TRACE, QUERY_PRESETS } from "@/data/mockTrace";
import { API_BASE, runTraceQuery } from "@/lib/api";
import type { TraceState } from "@/types/trace";

const API_HINT = `Could not reach ${API_BASE}`;

/** SSR-safe media query hook. */
function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(
    () => typeof window !== "undefined" && window.matchMedia(query).matches
  );
  useEffect(() => {
    const mql = window.matchMedia(query);
    const handler = () => setMatches(mql.matches);
    handler();
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, [query]);
  return matches;
}

/**
 * Builds a derived trace for a given query so switching presets visibly
 * re-routes the graph (relational → graph-heavy, conceptual → vector-heavy).
 */
function deriveTrace(query: string): TraceState {
  const preset = QUERY_PRESETS.find((p) => p.label === query);
  const intent = preset?.intent ?? MOCK_TRACE.weights.intent;
  if (intent === "conceptual") {
    return {
      ...MOCK_TRACE,
      query,
      weights: { vector: 0.8, graph: 0.2, intent: "conceptual" },
      confidence: {
        score: 0.86,
        uncertainty: 0.06,
        rationale:
          "Semantic query — the vector arm dominates. Confidence is slightly lower as no single graph path corroborates the answer.",
      },
    };
  }
  return { ...MOCK_TRACE, query };
}

export function TraceDashboard() {
  const [query, setQuery] = useState(MOCK_TRACE.query);
  const [trace, setTrace] = useState<TraceState>(MOCK_TRACE);
  const [loading, setLoading] = useState(true);
  const isDesktop = useMediaQuery("(min-width: 1024px)");

  /**
   * The chained integration flow:
   *   1. loading on
   *   2. POST /api/trace  →  extract every unique execution-path node id
   *   3. POST /api/subgraph with those ids
   *   4. merge + lay out into a TraceState, push to React state
   * Falls back to a derived sample trace if the backend is unreachable, so the
   * UI never ends up blank during a demo.
   */
  const handleSearch = useCallback(async (q: string) => {
    setQuery(q);
    setLoading(true);
    const toastId = toast.loading("Tracing query…", {
      description: "POST /api/trace → /api/subgraph",
    });
    try {
      const state = await runTraceQuery(q);
      setTrace(state);
      const tracedNodes = state.graph.nodes.filter((n) => n.active).length;
      const tracedEdges = state.graph.edges.filter((e) => e.active).length;
      toast.success("Trace computed", {
        id: toastId,
        description: `${tracedNodes} nodes · ${tracedEdges} traced edges · ${state.metrics.queryTimeSec}s`,
      });
    } catch (err) {
      console.error("[TraceRAG] live trace failed, falling back to sample:", err);
      setTrace(deriveTrace(q));
      toast.warning("Backend unreachable — showing sample trace", {
        id: toastId,
        description: `${API_HINT}. Wired correctly; this is the offline fallback.`,
      });
    } finally {
      setLoading(false);
    }
  }, []);

  // Attempt a live trace on mount for the default query (falls back to sample).
  useEffect(() => {
    void handleSearch(MOCK_TRACE.query);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex h-[100dvh] flex-col overflow-hidden bg-background">
      {isDesktop ? (
        <ResizablePanelGroup direction="horizontal" className="flex-1">
          <ResizablePanel
            defaultSize={35}
            minSize={26}
            maxSize={48}
            className="min-w-[320px]"
          >
            <LeftPane
              trace={trace}
              loading={loading}
              query={query}
              onQueryChange={handleSearch}
            />
          </ResizablePanel>
          <ResizableHandle withHandle />
          <ResizablePanel defaultSize={65} minSize={40}>
            <div className="h-full bg-white">
              <VisualTracer trace={trace} loading={loading} />
            </div>
          </ResizablePanel>
        </ResizablePanelGroup>
      ) : (
        <MobileLayout
          trace={trace}
          loading={loading}
          query={query}
          onQueryChange={handleSearch}
        />
      )}
    </div>
  );
}

function MobileLayout({
  trace,
  loading,
  query,
  onQueryChange,
}: {
  trace: TraceState;
  loading: boolean;
  query: string;
  onQueryChange: (q: string) => void;
}) {
  return (
    <Tabs defaultValue="log" className="flex h-full flex-col">
      <div className="flex justify-center border-b border-border bg-white/80 p-2 backdrop-blur">
        <TabsList>
          <TabsTrigger value="log">
            <PanelLeft className="h-4 w-4" />
            Execution Log
          </TabsTrigger>
          <TabsTrigger value="graph">
            <Network className="h-4 w-4" />
            Visual Tracer
          </TabsTrigger>
        </TabsList>
      </div>
      <TabsContent value="log" className="min-h-0 flex-1 data-[state=inactive]:hidden">
        <LeftPane
          trace={trace}
          loading={loading}
          query={query}
          onQueryChange={onQueryChange}
        />
      </TabsContent>
      <TabsContent
        value="graph"
        className="min-h-0 flex-1 bg-white data-[state=inactive]:hidden"
      >
        <VisualTracer trace={trace} loading={loading} />
      </TabsContent>
    </Tabs>
  );
}
