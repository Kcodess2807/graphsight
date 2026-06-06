import { useCallback, useEffect, useState } from "react";
import { History, PanelLeft, Network } from "lucide-react";
import { toast } from "sonner";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { LeftPane } from "@/components/left/LeftPane";
import { VisualTracer, type FocusRequest } from "@/components/right/VisualTracer";
import { HistorySidebar } from "@/components/left/HistorySidebar";
import { MOCK_TRACE, QUERY_PRESETS } from "@/data/mockTrace";
import {
  API_BASE,
  createSession,
  fetchSessionTraces,
  streamAnswer,
  hydrateTraceFromLog,
  listSessions,
  runTraceQuery,
  type ChatSessionDto,
} from "@/lib/api";
import { useSessionUser } from "@/lib/useSessionUser";
import type { TraceState } from "@/types/trace";

const API_HINT = `Could not reach ${API_BASE}`;

/** A blank canvas state for a fresh "New chat" (no nodes, no metrics). */
const EMPTY_TRACE: TraceState = {
  id: "trace_empty",
  query: "",
  computedAt: new Date(0).toISOString(),
  weights: { vector: 0.5, graph: 0.5, intent: "conceptual" },
  confidence: {
    score: 0,
    uncertainty: 0,
    rationale: "New session — run a query to begin.",
  },
  steps: [],
  metrics: {
    tokens: { used: 0, budget: 0, reductionPct: 0 },
    peakRamGb: 0,
    queryTimeSec: 0,
    nodesEvaluated: 0,
  },
  graph: { nodes: [], edges: [] },
};

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
  const [answer, setAnswer] = useState<string | null>(null);
  const [answering, setAnswering] = useState(false);
  const isDesktop = useMediaQuery("(min-width: 1024px)");

  // Full-graph focus: when on, the History sidebar and the Studio (left) column
  // are collapsed so the canvas owns the full screen width. Purely a layout
  // toggle — no trace/data is touched, so exiting restores the exact same view.
  const [graphFocus, setGraphFocus] = useState(false);
  const toggleGraphFocus = useCallback(() => setGraphFocus((v) => !v), []);

  // Answer-citation focus: clicking an entity name in the Answer pans/highlights
  // its node on the canvas. The nonce makes clicking the SAME citation twice
  // re-trigger the pan (a bare id wouldn't change and the effect wouldn't fire).
  const [focusNode, setFocusNode] = useState<FocusRequest | null>(null);
  const focusNodeById = useCallback((id: string) => {
    setFocusNode((prev) => ({ id, nonce: (prev?.nonce ?? 0) + 1 }));
  }, []);

  // Esc exits focus mode (standard fullscreen muscle-memory). The listener is
  // only attached while focused, so it never swallows Esc elsewhere in the app.
  useEffect(() => {
    if (!graphFocus) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setGraphFocus(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [graphFocus]);

  // Lazily generate the plain-language answer from a trace's context, AFTER
  // the graph has rendered — so it never adds to the trace's latency.
  const fetchAnswer = useCallback((state: TraceState) => {
    const ctx = state.context?.trim();
    if (!ctx) {
      setAnswer(null);
      return;
    }
    setAnswering(true);
    setAnswer(""); // start empty so the card streams in instead of popping whole
    // Stream tokens straight into state — the AnswerCard renders the growing
    // text with a typing cursor while `answering` stays true.
    streamAnswer(state.query, ctx, (partial) => setAnswer(partial))
      .catch(() => setAnswer(null))
      .finally(() => setAnswering(false));
  }, []);

  // --- Session / history state (only meaningful when signed in) ----------- //
  const { userId, email } = useSessionUser();
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [sessionsList, setSessionsList] = useState<ChatSessionDto[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const historyEnabled = Boolean(userId);

  // Load the user's sessions on sign-in (and clear them on sign-out).
  useEffect(() => {
    if (!userId) {
      setSessionsList([]);
      return;
    }
    let cancelled = false;
    setSessionsLoading(true);
    listSessions(userId)
      .then((rows) => {
        if (!cancelled) setSessionsList(rows);
      })
      .catch((err) => console.error("[TraceRAG] listSessions failed:", err))
      .finally(() => {
        if (!cancelled) setSessionsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [userId]);

  /**
   * The chained integration flow:
   *   1. loading on
   *   2. (signed in, no active session) → POST /api/sessions to start one
   *   3. POST /api/trace {session_id}  →  extract execution-path node ids
   *   4. POST /api/subgraph with those ids
   *   5. merge + lay out into a TraceState, push to React state
   * Falls back to a derived sample trace if the backend is unreachable, so the
   * UI never ends up blank during a demo. `persist` is false for the on-mount
   * demo query so we don't create a stray session every page load.
   */
  const handleSearch = useCallback(
    async (q: string, opts?: { persist?: boolean }) => {
      const persist = opts?.persist ?? true;
      setQuery(q);
      setLoading(true);
      const toastId = toast.loading("Tracing query…", {
        description: "POST /api/trace → /api/subgraph",
      });
      try {
        // Lazily start a session on the user's first query of a new chat.
        let sessionId = activeSessionId;
        if (persist && userId && !sessionId) {
          try {
            const created = await createSession(
              userId,
              q.slice(0, 30) || "New chat",
              email ?? undefined
            );
            sessionId = created.id;
            setActiveSessionId(created.id);
            setSessionsList((prev) => [created, ...prev]);
          } catch (err) {
            // Persistence is best-effort — never block retrieval on it.
            console.error("[TraceRAG] createSession failed:", err);
          }
        }

        const state = await runTraceQuery(q, sessionId ?? undefined);
        setTrace(state);
        setAnswer(null);
        fetchAnswer(state);
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
    },
    [activeSessionId, userId, email, fetchAnswer]
  );

  // New chat: drop the active session and blank the canvas.
  const handleNewChat = useCallback(() => {
    setActiveSessionId(null);
    setQuery("");
    setTrace(EMPTY_TRACE);
    setAnswer(null);
    setLoading(false);
  }, []);

  // Re-open a past session: hydrate the canvas from its latest stored trace,
  // with NO LLM call (only a pure /api/subgraph graph read).
  const handleSelectSession = useCallback(async (sessionId: string) => {
    setActiveSessionId(sessionId);
    setAnswer(null);
    setLoading(true);
    const toastId = toast.loading("Restoring session…");
    try {
      const logs = await fetchSessionTraces(sessionId);
      if (logs.length === 0) {
        setTrace(EMPTY_TRACE);
        setQuery("");
        toast.message("Empty session", {
          id: toastId,
          description: "No traces saved yet — run a query.",
        });
        return;
      }
      const latest = logs[logs.length - 1]; // oldest → newest
      const state = await hydrateTraceFromLog(latest);
      setTrace(state);
      setQuery(latest.query);
      toast.success("Session restored", {
        id: toastId,
        description: `${state.graph.nodes.length} nodes re-rendered (no LLM call).`,
      });
    } catch (err) {
      console.error("[TraceRAG] hydrate session failed:", err);
      toast.error("Could not restore session", {
        id: toastId,
        description: API_HINT,
      });
    } finally {
      setLoading(false);
    }
  }, []);

  // Attempt a live trace on mount for the default query (falls back to sample).
  // persist:false so the demo query never creates a session.
  useEffect(() => {
    void handleSearch(MOCK_TRACE.query, { persist: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex h-[100dvh] flex-col overflow-hidden bg-background">
      {isDesktop ? (
        <div className="flex min-h-0 flex-1">
          {graphFocus ? (
            // FOCUS MODE — sidebar + Studio column are simply not rendered, so
            // the canvas fills the whole row. VisualTracer still gets the toggle
            // (now showing a "minimize" icon) plus graphFocus so it can flip the
            // button label; Esc also exits (handler above).
            <div className="h-full w-full bg-white">
              <VisualTracer
                trace={trace}
                loading={loading}
                graphFocus
                onToggleFocus={toggleGraphFocus}
                focusNode={focusNode}
              />
            </div>
          ) : (
            <>
              {historyEnabled && (
                <HistorySidebar
                  sessions={sessionsList}
                  activeSessionId={activeSessionId}
                  loading={sessionsLoading}
                  onSelect={handleSelectSession}
                  onNewChat={handleNewChat}
                />
              )}
              <ResizablePanelGroup
                direction="horizontal"
                className="min-w-0 flex-1"
              >
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
                    onGraphSwitched={handleNewChat}
                    answer={answer}
                    answering={answering}
                    onCiteNode={focusNodeById}
                  />
                </ResizablePanel>
                <ResizableHandle withHandle />
                <ResizablePanel defaultSize={65} minSize={40}>
                  <div className="h-full bg-white">
                    {/* Pass the toggle here too so the user can ENTER focus mode
                        from the normal 3-column view. */}
                    <VisualTracer
                      trace={trace}
                      loading={loading}
                      graphFocus={false}
                      onToggleFocus={toggleGraphFocus}
                      focusNode={focusNode}
                    />
                  </div>
                </ResizablePanel>
              </ResizablePanelGroup>
            </>
          )}
        </div>
      ) : (
        <MobileLayout
          trace={trace}
          loading={loading}
          query={query}
          onQueryChange={handleSearch}
          answer={answer}
          answering={answering}
          onCiteNode={focusNodeById}
          focusNode={focusNode}
          historyEnabled={historyEnabled}
          sessions={sessionsList}
          sessionsLoading={sessionsLoading}
          activeSessionId={activeSessionId}
          onSelectSession={handleSelectSession}
          onNewChat={handleNewChat}
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
  answer,
  answering,
  onCiteNode,
  focusNode,
  historyEnabled,
  sessions,
  sessionsLoading,
  activeSessionId,
  onSelectSession,
  onNewChat,
}: {
  trace: TraceState;
  loading: boolean;
  query: string;
  onQueryChange: (q: string) => void;
  answer: string | null;
  answering: boolean;
  onCiteNode: (id: string) => void;
  focusNode: FocusRequest | null;
  historyEnabled: boolean;
  sessions: ChatSessionDto[];
  sessionsLoading: boolean;
  activeSessionId: string | null;
  onSelectSession: (sessionId: string) => void;
  onNewChat: () => void;
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
          {historyEnabled && (
            <TabsTrigger value="history">
              <History className="h-4 w-4" />
              History
            </TabsTrigger>
          )}
        </TabsList>
      </div>
      <TabsContent value="log" className="min-h-0 flex-1 data-[state=inactive]:hidden">
        <LeftPane
          trace={trace}
          loading={loading}
          query={query}
          onQueryChange={onQueryChange}
          onGraphSwitched={onNewChat}
          answer={answer}
          answering={answering}
          onCiteNode={onCiteNode}
        />
      </TabsContent>
      <TabsContent
        value="graph"
        className="min-h-0 flex-1 bg-white data-[state=inactive]:hidden"
      >
        <VisualTracer trace={trace} loading={loading} focusNode={focusNode} />
      </TabsContent>
      {historyEnabled && (
        <TabsContent
          value="history"
          className="min-h-0 flex-1 data-[state=inactive]:hidden"
        >
          <HistorySidebar
            sessions={sessions}
            activeSessionId={activeSessionId}
            loading={sessionsLoading}
            onSelect={onSelectSession}
            onNewChat={onNewChat}
            className="w-full border-r-0"
          />
        </TabsContent>
      )}
    </Tabs>
  );
}
