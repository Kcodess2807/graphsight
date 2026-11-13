// shared contract between the GraphRAG engine and the Studio UI
export type EntityType =
  | "PR"
  | "Commit"
  | "Service"
  | "Person"
  | "Document"
  | "Repo"
  | "Library"
  | "Ticket"
  | "Team"
  | "Tool"
  | "File";

export interface TraceNode {
  id: string;
  label: string;
  type: EntityType;
  // true when this node is on the highlighted answer path
  active: boolean;
  position: { x: number; y: number };
  similarity?: number;
  // fused router score = alpha*vector + beta*graph
  score?: number;
  meta?: {
    subtitle?: string;
    owner?: string;
    status?: string;
    timestamp?: string;
    snippet?: string;
    connections?: number;
    scoreGraph?: number;
    sourceUrl?: string;
    // lexical overlap with the final answer (0..1), measured by the tracer
    answerOverlap?: number | null;
    // age decay applied to the fused score: 1 = untouched, lower = older
    recency?: number;
    // null when the entity carries no timestamp, so it was never decayed
    ageDays?: number | null;
  };
}

export interface TraceEdge {
  id: string;
  source: string;
  target: string;
  confidence: number;
  active: boolean;
  // edge semantics, e.g. "MERGED_INTO", "CAUSED", "MENTIONS"
  relation?: string;
}

export interface TraceState {
  id: string;
  query: string;
  // the final answer, when the tracer captured one
  answer?: string | null;
  outcome?: "success" | "failure" | null;
  computedAt: string;
  metrics: { queryTimeSec: number };
  graph: {
    nodes: TraceNode[];
    edges: TraceEdge[];
  };
  context?: string;
}
