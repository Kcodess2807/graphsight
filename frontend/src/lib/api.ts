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
}

export interface TraceResponse {
  query: string;
  results: TraceResult[];
  trace_log: TraceLog;
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

const VALID_TYPES: EntityType[] = [
  "PR",
  "Service",
  "Person",
  "Document",
  "Repo",
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
  const nodeById = new Map<string, TraceNode>();
  for (const n of subgraph.nodes) {
    const active = n.requested === true || activeNodeIds.has(n.id);
    nodeById.set(n.id, {
      id: n.id,
      label: n.label ?? n.id,
      type: normalizeType(n.type),
      active,
      position: { x: 0, y: 0 }, // filled by dagre below
      meta: { subtitle: normalizeType(n.type) },
    });
  }
  // Active ids the subgraph forgot to return → synthesize stub nodes.
  for (const id of activeNodeIds) {
    if (!nodeById.has(id)) {
      nodeById.set(id, {
        id,
        label: id,
        type: "Document",
        active: true,
        position: { x: 0, y: 0 },
        meta: { subtitle: "Inferred from trace" },
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
  const nodeIds = extractNodeIds(trace.trace_log);
  const subgraph = await fetchSubgraph(nodeIds);
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
  const nodeIds = extractNodeIds(trace.trace_log);
  const subgraph = nodeIds.length
    ? await fetchSubgraph(nodeIds)
    : { nodes: [], edges: [] };
  return adaptToTraceState(log.query, trace, subgraph, 0);
}
