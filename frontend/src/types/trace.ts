// shared contract between the GraphRAG engine and the Studio UI
export type EntityType =
  | "PR"
  | "Service"
  | "Person"
  | "Document"
  | "Repo"
  | "Library"
  | "Ticket"
  | "Team"
  | "Tool";

export type RetrievalArm = "vector" | "graph";

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
  };
  // disconnected nodes hidden behind the "Show Orphans" toggle
  orphan?: boolean;
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

// intent-based router weights, alpha = vector, beta = graph
export interface RouterWeights {
  vector: number;
  graph: number;
  intent: "relational" | "conceptual";
}

export interface RouterConfidence {
  score: number;
  uncertainty: number;
  rationale: string;
}

export type StepStatus = "complete" | "active" | "pending";

export interface ExecutionStep {
  id: string;
  index: number;
  title: string;
  detail: string;
  status: StepStatus;
  badge?: string;
  arm?: RetrievalArm;
  durationMs?: number;
}

// only queryTimeSec is guaranteed; the rest depend on the backend contract
export interface TraceMetrics {
  tokens?: {
    used: number;
    budget: number;
    reductionPct: number;
  };
  peakRamGb?: number;
  queryTimeSec: number;
  nodesEvaluated?: number;
}

export interface TraceState {
  id: string;
  query: string;
  computedAt: string;
  weights: RouterWeights;
  confidence: RouterConfidence;
  steps: ExecutionStep[];
  metrics: TraceMetrics;
  graph: {
    nodes: TraceNode[];
    edges: TraceEdge[];
  };
  context?: string;
}
