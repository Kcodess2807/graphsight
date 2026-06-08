import dagre from "dagre";
import type { TraceEdge, TraceNode } from "@/types/trace";

// approximate rendered EntityNode card size; keep in sync with EntityNode.tsx
const NODE_W = 224;
const NODE_H = 72;

// dagre layered layout, left-to-right; returns a new array with position filled in
export function layoutGraph(
  nodes: TraceNode[],
  edges: TraceEdge[]
): TraceNode[] {
  const nodeIds = new Set(nodes.map((n) => n.id));
  const validEdges = edges.filter(
    (e) => nodeIds.has(e.source) && nodeIds.has(e.target)
  );

  // split connected nodes from orphans; we grid orphans separately
  const connected = new Set<string>();
  for (const e of validEdges) {
    connected.add(e.source);
    connected.add(e.target);
  }
  const orphans = nodes.filter((n) => !connected.has(n.id));

  const pos = new Map<string, { x: number; y: number }>();
  let maxY = 0;

  if (connected.size > 0) {
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
      if (connected.has(n.id)) g.setNode(n.id, { width: NODE_W, height: NODE_H });
    }
    for (const e of validEdges) {
      // weight active edges so the traced path stays on a short, straight rank
      g.setEdge(e.source, e.target, { weight: e.active ? 8 : 1 });
    }

    dagre.layout(g);

    for (const n of nodes) {
      const p = connected.has(n.id) ? g.node(n.id) : undefined;
      if (p) {
        const x = Math.round(p.x - NODE_W / 2);
        const y = Math.round(p.y - NODE_H / 2);
        pos.set(n.id, { x, y });
        maxY = Math.max(maxY, y + NODE_H);
      }
    }
  }

  // grid the orphans into a roughly-square block below the connected component
  if (orphans.length > 0) {
    const cols = Math.max(1, Math.ceil(Math.sqrt(orphans.length)));
    const gapX = NODE_W + 48;
    const gapY = NODE_H + 40;
    const startY = connected.size > 0 ? maxY + 80 : 40;
    orphans.forEach((n, i) => {
      const row = Math.floor(i / cols);
      const col = i % cols;
      pos.set(n.id, { x: 40 + col * gapX, y: startY + row * gapY });
    });
  }

  return nodes.map((n) => ({
    ...n,
    position: pos.get(n.id) ?? n.position ?? { x: 0, y: 0 },
  }));
}
