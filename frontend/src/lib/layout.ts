import dagre from "dagre";
import type { TraceEdge, TraceNode } from "@/types/trace";

/** Approximate rendered size of an EntityNode card (px). */
const NODE_W = 168;
const NODE_H = 60;

/**
 * The backend never sends X/Y coordinates, so we run a dagre layered layout to
 * arrange the sub-graph. Direction is left→right to mirror the reasoning flow
 * (seeds on the left, the answer service on the right). Active/traced nodes are
 * nudged onto the top ranks so the highlighted path reads cleanly.
 *
 * Returns a NEW array of nodes with `position` filled in; edges are untouched.
 */
export function layoutGraph(
  nodes: TraceNode[],
  edges: TraceEdge[]
): TraceNode[] {
  const g = new dagre.graphlib.Graph();
  g.setGraph({
    rankdir: "LR",
    nodesep: 48,
    ranksep: 120,
    marginx: 40,
    marginy: 40,
    ranker: "network-simplex",
  });
  g.setDefaultEdgeLabel(() => ({}));

  for (const n of nodes) {
    g.setNode(n.id, { width: NODE_W, height: NODE_H });
  }
  for (const e of edges) {
    // Only lay out edges whose endpoints exist, or dagre throws.
    if (g.hasNode(e.source) && g.hasNode(e.target)) {
      // Weight active edges so the traced path stays on a straight, short rank.
      g.setEdge(e.source, e.target, { weight: e.active ? 8 : 1 });
    }
  }

  dagre.layout(g);

  return nodes.map((n) => {
    const pos = g.node(n.id);
    return {
      ...n,
      position: pos
        ? { x: Math.round(pos.x - NODE_W / 2), y: Math.round(pos.y - NODE_H / 2) }
        : n.position ?? { x: 0, y: 0 },
    };
  });
}
