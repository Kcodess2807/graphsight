import type {
  EntityType,
  ExecutionStep,
  RouterConfidence,
  TraceEdge,
  TraceNode,
  TraceState,
} from "@/types/trace";
import { layoutGraph } from "@/lib/layout";

/** Base URL of the FastAPI backend (override with VITE_API_BASE). */
export const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) ??
  "http://localhost:8000";

// --------------------------------------------------------------------------- //
// Backend wire shapes (Endpoint A: /api/trace, Endpoint B: /api/subgraph)
// --------------------------------------------------------------------------- //
export interface TraceGraphHop {
  from_id: string;
  to_id: string;
  confidence: number;
}

export interface TraceLog {
  intent: { alpha: number; beta: number; type: string };
  execution_path: {
    vector_seeds: string[];
    /** Seeds reached by following a graph link from a vector seed. */
    linked_seeds?: string[];
    graph_hops: TraceGraphHop[];
  };
  metrics: { total_nodes_evaluated: number } & Record<string, number>;
}

/** A ranked answer entity from the router (id matches the sub-graph node id). */
export interface TraceResult {
  id: string;
  label?: string;
  type?: string;
  score_total?: number;
  score_vector?: number;
  score_graph?: number;
  documents?: { doc_id?: string; content?: string; path?: string }[];
  page_content?: string;
}

export interface TraceResponse {
  query: string;
  results: TraceResult[];
  trace_log: TraceLog;
  /** Assembled grounded context (for /api/answer); present on live traces. */
  context?: string;
}

export interface SubgraphNode {
  id: string;
  label: string;
  type: string;
  requested?: boolean;
}

export interface SubgraphEdge {
  source: string;
  target: string;
  confidence: number;
  relation?: string;
}

export interface SubgraphResponse {
  nodes: SubgraphNode[];
  edges: SubgraphEdge[];
}

// --------------------------------------------------------------------------- //
// History store (Postgres) wire shapes
// --------------------------------------------------------------------------- //
export interface ChatSessionDto {
  id: string;
  user_id: string;
  title: string;
  created_at: string;
}

/** One persisted execution. graph_payload = router `results`, execution_plan =
 *  the `trace_log` — together enough to rebuild the canvas with no LLM call. */
export interface TraceLogDto {
  id: string;
  session_id: string;
  query: string;
  execution_plan: TraceLog;
  graph_payload: TraceResult[];
  created_at: string;
}

// --------------------------------------------------------------------------- //
// Raw fetches
// --------------------------------------------------------------------------- //
async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`${path} → HTTP ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`${path} → HTTP ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

/** Endpoint A. Pass `sessionId` to persist the execution to Postgres history. */
export function fetchTrace(
  query: string,
  sessionId?: string
): Promise<TraceResponse> {
  return postJSON<TraceResponse>("/api/trace", {
    query,
    session_id: sessionId,
  });
}

/** Endpoint B. */
export function fetchSubgraph(nodeIds: string[]): Promise<SubgraphResponse> {
  return postJSON<SubgraphResponse>("/api/subgraph", { node_ids: nodeIds });
}

// --------------------------------------------------------------------------- //
// History endpoints (Postgres-backed)
// --------------------------------------------------------------------------- //
/** Create a new chat session, or rename an existing one when `sessionId` is set. */
export function createSession(
  userId: string,
  title: string,
  email?: string,
  sessionId?: string
): Promise<ChatSessionDto> {
  return postJSON<ChatSessionDto>("/api/sessions", {
    user_id: userId,
    title,
    email,
    session_id: sessionId,
  });
}

/** All of a user's sessions, newest first. */
export function listSessions(userId: string): Promise<ChatSessionDto[]> {
  return getJSON<ChatSessionDto[]>(
    `/api/sessions?user_id=${encodeURIComponent(userId)}`
  );
}

/** Full trace history for a session, oldest → newest. */
export function fetchSessionTraces(sessionId: string): Promise<TraceLogDto[]> {
  return getJSON<TraceLogDto[]>(
    `/api/sessions/${encodeURIComponent(sessionId)}/traces`
  );
}

// --------------------------------------------------------------------------- //
// Graph switching (hot-swap the active .lbug — per-repo graphs)
// --------------------------------------------------------------------------- //
export interface GraphInfo {
  id: string; // file name, e.g. "pallets__flask.lbug"
  label: string; // e.g. "pallets/flask"
  active: boolean;
}

/** List selectable graphs (the default + everything under backend/graphs/). */
export function listGraphs(): Promise<{
  graphs: GraphInfo[];
  active: string | null;
}> {
  return getJSON("/api/graphs");
}

/** Hot-swap the active graph; returns the new active id + node count. */
export function switchGraph(
  id: string
): Promise<{ active: string; label: string; nodes: number }> {
  return postJSON("/api/graphs/switch", { id });
}

// --------------------------------------------------------------------------- //
// Graph-aware suggested queries (built from the active graph's hub entities)
// --------------------------------------------------------------------------- //
export interface Suggestion {
  /** A ready-to-run question, e.g. "What did kdeldycke work on?". */
  query: string;
  /** The entity the question is about, e.g. "kdeldycke". */
  entity: string;
  /** That entity's type, e.g. "Person" — drives the chip icon/colour. */
  type: string;
}

/** Example questions THIS graph can actually answer. Empty list on any error. */
export async function fetchSuggestions(limit = 5): Promise<Suggestion[]> {
  try {
    const res = await getJSON<{ suggestions: Suggestion[] }>(
      `/api/suggestions?limit=${limit}`
    );
    return res.suggestions ?? [];
  } catch {
    return []; // suggestions are a nicety — never surface an error for them
  }
}

// --------------------------------------------------------------------------- //
// Plain-language answer (the "G" in GraphRAG) — grounded in the trace context
// --------------------------------------------------------------------------- //
const _answerCache = new Map<string, string>();

/** Generate a 2-3 sentence answer grounded in the retrieved context. Cached. */
export async function generateAnswer(
  query: string,
  context: string
): Promise<string> {
  const key = `${query}::${context.length}`;
  const cached = _answerCache.get(key);
  if (cached !== undefined) return cached;
  const res = await postJSON<{ answer: string }>("/api/answer", {
    query,
    context,
  });
  const answer = res.answer ?? "";
  if (answer) _answerCache.set(key, answer);
  return answer;
}

/**
 * Streaming variant: POSTs to /api/answer/stream and invokes `onToken` with the
 * cumulative text after each chunk, so the UI can render the answer as it's
 * generated. Resolves to the full answer (also cached). Falls back to the
 * blocking endpoint if the browser/response can't stream, so callers always get
 * a complete answer either way.
 */
export async function streamAnswer(
  query: string,
  context: string,
  onToken: (partial: string) => void
): Promise<string> {
  const key = `${query}::${context.length}`;
  const cached = _answerCache.get(key);
  if (cached !== undefined) {
    onToken(cached); // replay instantly so the card fills in one paint
    return cached;
  }

  const res = await fetch(`${API_BASE}/api/answer/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, context }),
  });
  // No streamable body (older browser / proxy buffered the whole thing) →
  // degrade gracefully to a single read.
  if (!res.ok || !res.body) {
    const fallback = await generateAnswer(query, context);
    onToken(fallback);
    return fallback;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let acc = "";
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    acc += decoder.decode(value, { stream: true });
    onToken(acc);
  }
  acc += decoder.decode(); // flush any multi-byte remainder
  const answer = acc.trim();
  if (answer) _answerCache.set(key, answer);
  return answer;
}

// --------------------------------------------------------------------------- //
// Helpers
// --------------------------------------------------------------------------- //

/** All unique node ids referenced anywhere in the execution path. */
export function extractNodeIds(log: TraceLog): string[] {
  const ids = new Set<string>(log.execution_path.vector_seeds);
  for (const id of log.execution_path.linked_seeds ?? []) ids.add(id);
  for (const hop of log.execution_path.graph_hops) {
    ids.add(hop.from_id);
    ids.add(hop.to_id);
  }
  return [...ids];
}

/**
 * Every node id the canvas should fetch a sub-graph for: the execution-path ids
 * PLUS the ranked answer `results`. This matters for vector-only queries (no
 * graph seeds/hops) — their execution_path is empty, so without the result ids
 * the /api/subgraph fetch comes back empty and the canvas degrades to typeless,
 * edgeless "Document" stubs stacked in a column. Including results gives the
 * real node types AND the edges between them, so dagre lays out a real graph.
 */
export function allTraceNodeIds(trace: TraceResponse): string[] {
  const ids = new Set<string>(extractNodeIds(trace.trace_log));
  for (const r of trace.results ?? []) if (r?.id) ids.add(r.id);
  return [...ids];
}

const VALID_TYPES: EntityType[] = [
  "PR",
  "Service",
  "Person",
  "Document",
  "Repo",
  "Library",
  "Ticket",
  "Team",
  "Tool",
];

/** Coerce a backend type string into a known EntityType (default Document). */
function normalizeType(type: string | undefined): EntityType {
  if (!type) return "Document";
  const hit = VALID_TYPES.find((t) => t.toLowerCase() === type.toLowerCase());
  return hit ?? "Document";
}

/** Best short snippet to show on hover: first non-empty source chunk, capped. */
function resultSnippet(r: TraceResult): string | undefined {
  const doc = r.documents?.find((d) => (d.content ?? "").trim().length > 0);
  const text = (doc?.content ?? r.page_content ?? "").trim();
  if (!text) return undefined;
  return text.length > 240 ? `${text.slice(0, 240)}…` : text;
}

/** A web source URL (e.g. a GitHub PR link) stored as the Document `path`. */
function resultSourceUrl(r: TraceResult): string | undefined {
  return r.documents?.find((d) => /^https?:\/\//.test(d.path ?? ""))?.path;
}

// --------------------------------------------------------------------------- //
// On-demand LLM summary (lazy, called on node hover; server caches by key)
// --------------------------------------------------------------------------- //
const _summaryCache = new Map<string, string>();

/** Fetch a one-sentence summary of a node's snippet. Cached client- and
 *  server-side, so each node is summarized at most once. */
export async function summarizeNode(key: string, text: string): Promise<string> {
  const cached = _summaryCache.get(key);
  if (cached !== undefined) return cached;
  const res = await postJSON<{ summary: string }>("/api/summarize", { key, text });
  const summary = res.summary ?? "";
  if (summary) _summaryCache.set(key, summary);
  return summary;
}

/**
 * The backend gives no explicit router-confidence score, so we derive one from
 * the traversal: mean graph-hop confidence is the point estimate, and the
 * spread (½ the range) is the uncertainty band. Sensible fallback when the
 * answer came purely from the vector arm (no hops).
 */
function deriveConfidence(log: TraceLog): RouterConfidence {
  const hops = log.execution_path.graph_hops;
  if (hops.length === 0) {
    return {
      score: 0.78,
      uncertainty: 0.08,
      rationale:
        "Answer came from the vector arm with no corroborating graph hops — confidence derived from a conservative prior.",
    };
  }
  const confs = hops.map((h) => h.confidence);
  const mean = confs.reduce((a, b) => a + b, 0) / confs.length;
  const spread = (Math.max(...confs) - Math.min(...confs)) / 2;
  const uncertainty = Math.min(0.2, Math.max(0.02, spread || 0.03));
  return {
    score: Math.max(0, Math.min(1, mean)),
    uncertainty,
    rationale: `Derived from ${hops.length} graph hop${
      hops.length === 1 ? "" : "s"
    } (mean confidence ${mean.toFixed(2)}). Band reflects spread across the traced edges.`,
  };
}

/** Synthesize the 3-step execution stepper from the trace log. */
function buildSteps(log: TraceLog): ExecutionStep[] {
  const seeds = log.execution_path.vector_seeds.length;
  const hops = log.execution_path.graph_hops.length;
  const evaluated = log.metrics.total_nodes_evaluated;
  return [
    {
      id: "step-1",
      index: 1,
      title: "Vector Recall",
      detail: `Seeded retrieval with ${seeds} semantic chunk${seeds === 1 ? "" : "s"}.`,
      status: "complete",
      badge: `${seeds} seed${seeds === 1 ? "" : "s"}`,
      arm: "vector",
    },
    {
      id: "step-2",
      index: 2,
      title: "Graph Traversal",
      detail: `Walked ${hops} edge${hops === 1 ? "" : "s"} across the relationship graph.`,
      status: "complete",
      badge: `${hops} hop${hops === 1 ? "" : "s"}`,
      arm: "graph",
    },
    {
      id: "step-3",
      index: 3,
      title: "Context Assembly",
      detail: `Evaluated ${evaluated} node${evaluated === 1 ? "" : "s"} to assemble the grounded context.`,
      status: "complete",
      badge: `${evaluated} nodes`,
    },
  ];
}

/**
 * Merge Endpoint A (trace_log) + Endpoint B (subgraph) into the single
 * `TraceState` the UI already renders. This is the whole point of the adapter:
 * downstream components never learn the backend exists.
 *
 * Visual merging:
 *   - active = node is in the execution path OR flagged `requested`
 *   - dimmed/background = everything else (the UI renders these at opacity-40)
 *   - active edges = those matching a graph_hop (added if the subgraph omits them)
 */
export function adaptToTraceState(
  query: string,
  trace: TraceResponse,
  subgraph: SubgraphResponse,
  elapsedMs: number
): TraceState {
  const log = trace.trace_log;
  const resultById = new Map((trace.results ?? []).map((r) => [r.id, r]));

  const activeNodeIds = new Set(extractNodeIds(log));
  // Fallback: if the router traversed no graph path (e.g. a query that matched
  // no entity), treat the ranked answer `results` as the active set so the
  // canvas shows the retrieved candidates instead of going blank.
  const isEmptyPath = activeNodeIds.size === 0;
  if (isEmptyPath) {
    for (const r of trace.results ?? []) if (r?.id) activeNodeIds.add(r.id);
  }
  // Directed key for matching hops against edges (undirected fallback below).
  const hopKey = (a: string, b: string) => `${a}__${b}`;
  const activeHopKeys = new Set(
    log.execution_path.graph_hops.flatMap((h) => [
      hopKey(h.from_id, h.to_id),
      hopKey(h.to_id, h.from_id),
    ])
  );

  // --- nodes: start from the subgraph, then ensure every active id exists ---
  // Answer nodes (those in `results`) carry the router scores + source snippet
  // we surface on the node chip and hover card.
  const nodeById = new Map<string, TraceNode>();
  for (const n of subgraph.nodes) {
    const active = n.requested === true || activeNodeIds.has(n.id);
    const r = resultById.get(n.id);
    const type = normalizeType(n.type);
    nodeById.set(n.id, {
      id: n.id,
      label: n.label ?? n.id,
      type,
      active,
      position: { x: 0, y: 0 }, // filled by dagre below
      similarity: r?.score_vector ? r.score_vector : undefined,
      score: r?.score_total,
      meta: {
        subtitle: type,
        snippet: r ? resultSnippet(r) : undefined,
        scoreGraph: r?.score_graph,
        sourceUrl: r ? resultSourceUrl(r) : undefined,
      },
    });
  }
  // Active ids the subgraph forgot to return → synthesize from the result row.
  for (const id of activeNodeIds) {
    if (!nodeById.has(id)) {
      const r = resultById.get(id);
      const type = r?.type ? normalizeType(r.type) : "Document";
      nodeById.set(id, {
        id,
        label: r?.label ?? id,
        type,
        active: true,
        position: { x: 0, y: 0 },
        similarity: r?.score_vector ? r.score_vector : undefined,
        score: r?.score_total,
        meta: {
          subtitle: r?.type ? type : "Inferred from trace",
          snippet: r ? resultSnippet(r) : undefined,
          scoreGraph: r?.score_graph,
          sourceUrl: r ? resultSourceUrl(r) : undefined,
        },
      });
    }
  }

  // --- edges: subgraph edges + any traced hop missing from them ---
  const edges: TraceEdge[] = [];
  const seenEdge = new Set<string>();
  for (const [i, e] of subgraph.edges.entries()) {
    // In normal mode an edge is active when it matches a traced hop. In the
    // empty-path fallback, connect the result cluster using edges whose both
    // endpoints are in the active (results) set.
    const active =
      activeHopKeys.has(hopKey(e.source, e.target)) ||
      (isEmptyPath &&
        activeNodeIds.has(e.source) &&
        activeNodeIds.has(e.target));
    seenEdge.add(hopKey(e.source, e.target));
    edges.push({
      id: `e-${e.source}-${e.target}-${i}`,
      source: e.source,
      target: e.target,
      confidence: e.confidence,
      active,
      relation: e.relation,
    });
  }
  log.execution_path.graph_hops.forEach((h, i) => {
    if (
      !seenEdge.has(hopKey(h.from_id, h.to_id)) &&
      nodeById.has(h.from_id) &&
      nodeById.has(h.to_id)
    ) {
      edges.push({
        id: `hop-${h.from_id}-${h.to_id}-${i}`,
        source: h.from_id,
        target: h.to_id,
        confidence: h.confidence,
        active: true,
      });
    }
  });

  // Connection count (degree) per node from the rendered edges → hover card.
  const degree = new Map<string, number>();
  for (const e of edges) {
    degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
    degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
  }
  for (const node of nodeById.values()) {
    node.meta = { ...node.meta, connections: degree.get(node.id) ?? 0 };
  }

  // --- layout (backend has no coordinates) ---
  const positioned = layoutGraph([...nodeById.values()], edges);

  return {
    id: `trace_${Date.now().toString(36)}`,
    query,
    computedAt: new Date().toISOString(),
    weights: {
      vector: log.intent.alpha,
      graph: log.intent.beta,
      intent: log.intent.type === "conceptual" ? "conceptual" : "relational",
    },
    confidence: deriveConfidence(log),
    steps: buildSteps(log),
    metrics: {
      // queryTime is measured client-side (real round-trip); token/RAM aren't in
      // the contract yet, so we surface the real "nodes evaluated" instead.
      tokens: { used: 0, budget: 0, reductionPct: 0 },
      peakRamGb: 0,
      queryTimeSec: +(elapsedMs / 1000).toFixed(2),
      nodesEvaluated: log.metrics.total_nodes_evaluated,
    },
    graph: { nodes: positioned, edges },
    context: trace.context,
  };
}

/**
 * The full chained flow described in the brief:
 *   1. POST /api/trace
 *   2. extract every unique node id from the execution path
 *   3. POST /api/subgraph with those ids
 *   4. merge + lay out into a TraceState
 * Returns the adapted state plus the measured latency.
 */
export async function runTraceQuery(
  query: string,
  sessionId?: string
): Promise<TraceState> {
  const t0 = performance.now();
  const trace = await fetchTrace(query, sessionId);
  const nodeIds = allTraceNodeIds(trace);
  const subgraph = nodeIds.length
    ? await fetchSubgraph(nodeIds)
    : { nodes: [], edges: [] };
  const elapsed = performance.now() - t0;
  return adaptToTraceState(query, trace, subgraph, elapsed);
}

/**
 * Rebuild a canvas `TraceState` from a persisted trace log — for re-rendering a
 * past session WITHOUT calling the LLM. We already stored the router `results`
 * (graph_payload) and `trace_log` (execution_plan); the only thing missing is
 * the sub-graph geometry, which we fetch from `/api/subgraph` (a pure graph
 * read — no embedding, no intent LLM, no generation). The result runs through
 * the exact same adapter as a live query, so the canvas is pixel-identical.
 */
export async function hydrateTraceFromLog(
  log: TraceLogDto
): Promise<TraceState> {
  const trace: TraceResponse = {
    query: log.query,
    results: log.graph_payload ?? [],
    trace_log: log.execution_plan,
  };
  const nodeIds = allTraceNodeIds(trace);
  const subgraph = nodeIds.length
    ? await fetchSubgraph(nodeIds)
    : { nodes: [], edges: [] };
  return adaptToTraceState(log.query, trace, subgraph, 0);
}
