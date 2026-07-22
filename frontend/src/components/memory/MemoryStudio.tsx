import { useCallback, useEffect, useRef, useState } from "react";
import { AppLayout } from "./AppLayout";
import type { SuggestedTrace } from "./CommandPanel";
import {
  createSession,
  fetchSessionTraces,
  fetchSuggestions,
  hydrateTraceFromLog,
  listSessions,
  runTraceQuery,
  streamAnswer,
  type ChatSessionDto,
} from "@/lib/api";
import { useSessionUser } from "@/lib/useSessionUser";
import { MOCK_TRACE, QUERY_PRESETS } from "@/data/mockTrace";
import type { TraceState } from "@/types/trace";

const RECENT_KEY = "graphsight.memory.recent";

const EMPTY_TRACE: TraceState = {
  id: "trace_empty",
  query: "",
  computedAt: new Date(0).toISOString(),
  weights: { vector: 0.5, graph: 0.5, intent: "conceptual" },
  confidence: { score: 0, uncertainty: 0, rationale: "Memory idle." },
  steps: [],
  metrics: { queryTimeSec: 0 },
  graph: { nodes: [], edges: [] },
};

function loadRecent(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    return raw ? (JSON.parse(raw) as string[]) : [];
  } catch {
    return [];
  }
}

/**
 * Live memory-tool studio. Same data flow as the classic dashboard —
 * runTraceQuery then streamAnswer off the trace latency, with per-user
 * session persistence — rendered through the monochrome AppLayout.
 * Falls back to the sample trace when the backend is unreachable.
 */
export function MemoryStudio() {
  const [trace, setTrace] = useState<TraceState>(EMPTY_TRACE);
  const [tracing, setTracing] = useState(false);
  const [answer, setAnswer] = useState<string | null>(null);
  const [recent, setRecent] = useState<string[]>(loadRecent);
  const [suggestions, setSuggestions] = useState<SuggestedTrace[]>(
    QUERY_PRESETS.map((p) => ({ label: p.label, query: p.label }))
  );
  // guards against a stale request overwriting a newer query's state
  const queryEpoch = useRef(0);

  // session/history state, only meaningful when signed in
  const { userId, email } = useSessionUser();
  const [sessions, setSessions] = useState<ChatSessionDto[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const historyEnabled = Boolean(userId);

  // load sessions on sign-in, clear on sign-out
  useEffect(() => {
    if (!userId) {
      setSessions([]);
      setActiveSessionId(null);
      return;
    }
    let cancelled = false;
    listSessions(userId)
      .then((rows) => {
        if (!cancelled) setSessions(rows);
      })
      .catch((err) => console.error("[Graphsight] listSessions failed:", err));
    return () => {
      cancelled = true;
    };
  }, [userId]);

  // graph-aware suggestions from the backend; presets remain the fallback
  useEffect(() => {
    fetchSuggestions(6).then((rows) => {
      if (rows.length > 0) {
        setSuggestions(rows.map((s) => ({ label: s.query, query: s.query })));
      }
    });
  }, []);

  const rememberQuery = useCallback((q: string) => {
    setRecent((prev) => {
      const next = [q, ...prev.filter((r) => r !== q)].slice(0, 6);
      try {
        localStorage.setItem(RECENT_KEY, JSON.stringify(next));
      } catch {
        // storage full/blocked — recents just won't persist
      }
      return next;
    });
  }, []);

  const handleQuery = useCallback(
    async (q: string) => {
      const epoch = ++queryEpoch.current;
      setTracing(true);
      setAnswer(null);
      rememberQuery(q);
      try {
        // lazily start a session on the first query of a new chat
        let sessionId = activeSessionId;
        if (userId && !sessionId) {
          try {
            const created = await createSession(
              userId,
              q.slice(0, 30) || "New chat",
              email ?? undefined
            );
            sessionId = created.id;
            setActiveSessionId(created.id);
            setSessions((prev) => [created, ...prev]);
          } catch (err) {
            // persistence is best-effort, never block retrieval on it
            console.error("[Graphsight] createSession failed:", err);
          }
        }

        const state = await runTraceQuery(q, sessionId ?? undefined);
        if (epoch !== queryEpoch.current) return;
        setTrace(state);
        const ctx = state.context?.trim();
        if (ctx) {
          setAnswer(""); // stream in instead of popping whole
          streamAnswer(q, ctx, (partial) => {
            if (epoch === queryEpoch.current) setAnswer(partial);
          }).catch(() => {
            if (epoch === queryEpoch.current) setAnswer(null);
          });
        }
      } catch (err) {
        console.error("[Graphsight] live trace failed, showing sample:", err);
        if (epoch !== queryEpoch.current) return;
        setTrace({ ...MOCK_TRACE, id: `trace_${q}`, query: q });
        setAnswer(
          "Backend unreachable — showing the sample trace so the canvas stays explorable."
        );
      } finally {
        if (epoch === queryEpoch.current) setTracing(false);
      }
    },
    [activeSessionId, userId, email, rememberQuery]
  );

  // re-open a past session: hydrate from its latest stored trace, no llm call
  const handleSelectSession = useCallback(async (sessionId: string) => {
    const epoch = ++queryEpoch.current;
    setActiveSessionId(sessionId);
    setAnswer(null);
    setTracing(true);
    try {
      const logs = await fetchSessionTraces(sessionId);
      if (epoch !== queryEpoch.current) return;
      if (logs.length === 0) {
        setTrace(EMPTY_TRACE);
        return;
      }
      const latest = logs[logs.length - 1];
      const state = await hydrateTraceFromLog(latest);
      if (epoch !== queryEpoch.current) return;
      setTrace(state);
    } catch (err) {
      console.error("[Graphsight] hydrate session failed:", err);
    } finally {
      if (epoch === queryEpoch.current) setTracing(false);
    }
  }, []);

  // new chat: drop the active session and blank the canvas
  const handleNewChat = useCallback(() => {
    queryEpoch.current++;
    setActiveSessionId(null);
    setTrace(EMPTY_TRACE);
    setAnswer(null);
    setTracing(false);
  }, []);

  return (
    <AppLayout
      trace={trace}
      tracing={tracing}
      answer={answer}
      suggestions={suggestions}
      recentQueries={recent}
      onQuery={handleQuery}
      sessions={historyEnabled ? sessions : undefined}
      activeSessionId={activeSessionId}
      onSelectSession={historyEnabled ? handleSelectSession : undefined}
      onNewChat={handleNewChat}
    />
  );
}
