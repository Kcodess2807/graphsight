/**
 * TraceRAG — the rigid contract between the GraphRAG engine and the Studio UI.
 *
 * A `TraceState` is the complete, serialisable record of how the hybrid router
 * answered one query: the intent-based vector/graph weights, the router's
 * confidence (with an uncertainty band), the ordered execution steps, the
 * footprint metrics, and the `.lbug` sub-graph that was touched — including
 * which nodes/edges form the highlighted "traced path".
 *
 * This mirrors the backend schema in `tracerag/`:
 *   - entity types come from config.ENTITY_LABELS (+ Document)
 *   - edges carry a `confidence` (RELATES_TO.confidence)
 *   - router weights are alpha (vector) / beta (graph), summing to 1
 */

export type EntityType =
  | "PR"
  | "Service"
  | "Person"
  | "Document"
  | "Repo"
  | "Ticket"
  | "Team"
  | "Tool";

export type RetrievalArm = "vector" | "graph";

/** A single node in the touched `.lbug` sub-graph. */
export interface TraceNode {
  id: string;
  /** Human-readable canonical label, e.g. "PR #402" or "payments-service". */
  label: string;
  type: EntityType;
  /** True when this node is part of the highlighted answer path. */
  active: boolean;
  /** Layout position on the canvas (graph coordinates). */
  position: { x: number; y: number };
  /** Cosine similarity to the query, when this node came from the vector arm. */
  similarity?: number;
  /** Optional metadata surfaced in the hover card. */
  meta?: {
    subtitle?: string;
    owner?: string;
    status?: string;
    timestamp?: string;
    snippet?: string;
  };
  /** True for disconnected nodes hidden behind the "Show Orphans" toggle. */
  orphan?: boolean;
}

/** A directed edge in the touched sub-graph (RELATES_TO / MENTIONS). */
export interface TraceEdge {
  id: string;
  source: string;
  target: string;
  /** RELATES_TO.confidence — strength of the relationship in [0, 1]. */
  confidence: number;
  /** True when this edge lies on the highlighted traced path. */
  active: boolean;
  /** Edge semantics, e.g. "MERGED_INTO", "CAUSED", "MENTIONS". */
  relation?: string;
}

/** Dynamic intent-based router weights (alpha = vector, beta = graph). */
export interface RouterWeights {
  /** α — vector arm weight in [0, 1]. */
  vector: number;
  /** β — graph arm weight in [0, 1]. */
  graph: number;
  /** Which arm the router decided dominates this query. */
  intent: "relational" | "conceptual";
}

/** Router uncertainty: a point estimate plus a symmetric ± band. */
export interface RouterConfidence {
  /** Point estimate in [0, 1]. */
  score: number;
  /** Symmetric uncertainty band in [0, 1], e.g. 0.04 → ±4%. */
  uncertainty: number;
  /** Short explanation of what drove the score (shown in a tooltip). */
  rationale: string;
}

export type StepStatus = "complete" | "active" | "pending";

/** One row in the vertical execution stepper. */
export interface ExecutionStep {
  id: string;
  index: number;
  title: string;
  detail: string;
  status: StepStatus;
  /** Optional badge metric, e.g. "8 chunks" or "3 hops". */
  badge?: string;
  arm?: RetrievalArm;
  /** Wall-clock duration of the step in milliseconds. */
  durationMs?: number;
}

/**
 * The footprint metrics shown in the left-pane footer cards. Only `queryTimeSec`
 * is guaranteed; the rest are optional because the live backend contract may
 * not supply them. The footer renders whichever metrics are present.
 */
export interface TraceMetrics {
  tokens?: {
    used: number;
    budget: number;
    /** % token reduction vs. naive full-context RAG (the "good news" stat). */
    reductionPct: number;
  };
  /** Peak resident memory in gigabytes. */
  peakRamGb?: number;
  /** End-to-end query latency in seconds (measured client-side for live data). */
  queryTimeSec: number;
  /** total_nodes_evaluated from the backend trace_log.metrics. */
  nodesEvaluated?: number;
}

/** The complete trace for one query. */
export interface TraceState {
  id: string;
  query: string;
  /** ISO timestamp the trace was computed. */
  computedAt: string;
  weights: RouterWeights;
  confidence: RouterConfidence;
  steps: ExecutionStep[];
  metrics: TraceMetrics;
  graph: {
    nodes: TraceNode[];
    edges: TraceEdge[];
  };
}
