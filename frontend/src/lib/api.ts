import type {
  EntityType,
  ExecutionStep,
  RouterConfidence,
  TraceEdge,
  TraceNode,
  TraceState,
} from "@/types/trace";
import { layoutGraph } from "@/lib/layout";
import { getAuthToken } from "@/lib/authToken";

// override with VITE_API_BASE
export const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) ??
  "http://localhost:8000";

// merge a Bearer token into request headers when the user is signed in.
// Returns the base headers unchanged when there's no token (unauthenticated /
// Clerk disabled), which the backend's dev-bypass mode still accepts locally.
async function authHeaders(
  base: Record<string, string> = {}
): Promise<Record<string, string>> {
  const token = await getAuthToken();
  return token ? { ...base, Authorization: `Bearer ${token}` } : base;
}

export interface TraceGraphHop {
  from_id: string;
  to_id: string;
  confidence: number;
}

export interface TraceLog {
  intent: { alpha: number; beta: number; type: string };
  execution_path: {
    vector_seeds: string[];
    linked_seeds?: string[];
    graph_hops: TraceGraphHop[];
  };
  metrics: { total_nodes_evaluated: number } & Record<string, number>;
}

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

export interface ChatSessionDto {
  id: string;
  user_id: string;
  title: string;
  created_at: string;
}

// graph_payload = router results, execution_plan = trace_log; enough to rebuild the canvas
export interface TraceLogDto {
  id: string;
  session_id: string;
  query: string;
  execution_plan: TraceLog;
  graph_payload: TraceResult[];
  created_at: string;
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: await authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`${path} → HTTP ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: await authHeaders(),
  });
  if (!res.ok) {
    throw new Error(`${path} → HTTP ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

// pass sessionId to persist the execution to history
export function fetchTrace(
  query: string,
  sessionId?: string
): Promise<TraceResponse> {
  return postJSON<TraceResponse>("/api/trace", {
    query,
    session_id: sessionId,
  });
}

export function fetchSubgraph(nodeIds: string[]): Promise<SubgraphResponse> {
  return postJSON<SubgraphResponse>("/api/subgraph", { node_ids: nodeIds });
}

// create a new session, or rename an existing one when sessionId is set
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

export function listSessions(userId: string): Promise<ChatSessionDto[]> {
  return getJSON<ChatSessionDto[]>(
    `/api/sessions?user_id=${encodeURIComponent(userId)}`
  );
}

export function fetchSessionTraces(sessionId: string): Promise<TraceLogDto[]> {
  return getJSON<TraceLogDto[]>(
    `/api/sessions/${encodeURIComponent(sessionId)}/traces`
  );
}

export interface GraphInfo {
  id: string;
  label: string;
  active: boolean;
}

export function listGraphs(): Promise<{
  graphs: GraphInfo[];
  active: string | null;
}> {
  return getJSON("/api/graphs");
}

// hot-swap the active graph; returns the new active id + node count
export function switchGraph(
  id: string
): Promise<{ active: string; label: string; nodes: number }> {
  return postJSON("/api/graphs/switch", { id });
}

export interface Suggestion {
  query: string;
  entity: string;
  type: string;
}

// example questions this graph can answer; empty list on any error
export async function fetchSuggestions(limit = 5): Promise<Suggestion[]> {
  try {
    const res = await getJSON<{ suggestions: Suggestion[] }>(
      `/api/suggestions?limit=${limit}`
    );
    return res.suggestions ?? [];
  } catch {
    return [];
  }
}

const _answerCache = new Map<string, string>();

// generate a short answer grounded in the retrieved context; cached
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

// streams /api/answer/stream, calling onToken with cumulative text; falls back to blocking
export async function streamAnswer(
  query: string,
  context: string,
  onToken: (partial: string) => void
): Promise<string> {
  const key = `${query}::${context.length}`;
  const cached = _answerCache.get(key);
  if (cached !== undefined) {
    onToken(cached);
    return cached;
  }

  const res = await fetch(`${API_BASE}/api/answer/stream`, {
    method: "POST",
    headers: await authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ query, context }),
  });
  // no streamable body (older browser / buffering proxy) - fall back to a single read
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

// all unique node ids referenced anywhere in the execution path
export function extractNodeIds(log: TraceLog): string[] {
  const ids = new Set<string>(log.execution_path.vector_seeds);
  for (const id of log.execution_path.linked_seeds ?? []) ids.add(id);
  for (const hop of log.execution_path.graph_hops) {
    ids.add(hop.from_id);
    ids.add(hop.to_id);
  }
  return [...ids];
}

// execution-path ids plus the ranked results; results matter for vector-only queries
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

// coerce a backend type string into a known EntityType (default Document)
function normalizeType(type: string | undefined): EntityType {
  if (!type) return "Document";
  const hit = VALID_TYPES.find((t) => t.toLowerCase() === type.toLowerCase());
  return hit ?? "Document";
}

// short hover snippet: first non-empty source chunk, capped
function resultSnippet(r: TraceResult): string | undefined {
  const doc = r.documents?.find((d) => (d.content ?? "").trim().length > 0);
  const text = (doc?.content ?? r.page_content ?? "").trim();
  if (!text) return undefined;
  return text.length > 240 ? `${text.slice(0, 240)}…` : text;
}

// web source url (e.g. a GitHub PR link) stored as the Document path
function resultSourceUrl(r: TraceResult): string | undefined {
  return r.documents?.find((d) => /^https?:\/\//.test(d.path ?? ""))?.path;
}

const _summaryCache = new Map<string, string>();

// one-sentence summary of a node's snippet; cached client- and server-side
export async function summarizeNode(key: string, text: string): Promise<string> {
  const cached = _summaryCache.get(key);
  if (cached !== undefined) return cached;
  const res = await postJSON<{ summary: string }>("/api/summarize", { key, text });
  const summary = res.summary ?? "";
  if (summary) _summaryCache.set(key, summary);
  return summary;
}

// derive a confidence from the traversal: mean hop confidence, spread as the band
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

// synthesize the 3-step execution stepper from the trace log
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

// merge trace_log + subgraph into the single TraceState the UI renders
export function adaptToTraceState(
  query: string,
  trace: TraceResponse,
  subgraph: SubgraphResponse,
  elapsedMs: number
): TraceState {
  const log = trace.trace_log;
  const resultById = new Map((trace.results ?? []).map((r) => [r.id, r]));

  const activeNodeIds = new Set(extractNodeIds(log));
  // no traversed path: use the ranked results as the active set so the canvas isn't blank
  const isEmptyPath = activeNodeIds.size === 0;
  if (isEmptyPath) {
    for (const r of trace.results ?? []) if (r?.id) activeNodeIds.add(r.id);
  }
  // directed key for matching hops against edges
  const hopKey = (a: string, b: string) => `${a}__${b}`;
  const activeHopKeys = new Set(
    log.execution_path.graph_hops.flatMap((h) => [
      hopKey(h.from_id, h.to_id),
      hopKey(h.to_id, h.from_id),
    ])
  );

  // nodes: start from the subgraph, then ensure every active id exists
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
      position: { x: 0, y: 0 }, // filled by dagre
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
  // active ids the subgraph didn't return: synthesize from the result row
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

  // edges: subgraph edges + any traced hop missing from them
  const edges: TraceEdge[] = [];
  const seenEdge = new Set<string>();
  for (const [i, e] of subgraph.edges.entries()) {
    // active when it matches a traced hop, or in empty-path mode both ends are active
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

  // degree per node from the rendered edges, for the hover card
  const degree = new Map<string, number>();
  for (const e of edges) {
    degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
    degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
  }
  for (const node of nodeById.values()) {
    node.meta = { ...node.meta, connections: degree.get(node.id) ?? 0 };
  }

  // layout (backend has no coordinates)
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
      // queryTime is measured client-side; token/RAM aren't in the contract yet
      tokens: { used: 0, budget: 0, reductionPct: 0 },
      peakRamGb: 0,
      queryTimeSec: +(elapsedMs / 1000).toFixed(2),
      nodesEvaluated: log.metrics.total_nodes_evaluated,
    },
    graph: { nodes: positioned, edges },
    context: trace.context,
  };
}

// trace -> extract node ids -> subgraph -> merge + lay out into a TraceState
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

// rebuild a TraceState from a persisted log (re-fetches subgraph geometry, no LLM)
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
