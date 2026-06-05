import { useEffect, useMemo, useRef, useState } from "react";
import ReactFlow, {
  Background,
  BackgroundVariant,
  MarkerType,
  ReactFlowProvider,
  useReactFlow,
  useNodesState,
  useEdgesState,
  type Edge,
  type Node,
} from "reactflow";
import { motion } from "framer-motion";
import { Route, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { EntityNode } from "./EntityNode";
import { TracedEdge } from "./TracedEdge";
import { GraphControls } from "./GraphControls";
import { GraphLegend } from "./GraphLegend";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { layoutGraph } from "@/lib/layout";
import type { TraceState } from "@/types/trace";

const nodeTypes = { entity: EntityNode };
const edgeTypes = { traced: TracedEdge };

/** A request to focus a specific node, carrying a monotonically-increasing
 *  nonce so clicking the SAME citation twice still re-triggers the pan. */
export interface FocusRequest {
  id: string;
  nonce: number;
}

interface VisualTracerProps {
  trace: TraceState;
  loading: boolean;
  /** Full-graph focus mode state + toggle, owned by TraceDashboard (the only
   *  component that can collapse the sibling columns). Optional → mobile omits. */
  graphFocus?: boolean;
  onToggleFocus?: () => void;
  /** Pan/highlight this node (driven by answer-citation clicks). */
  focusNode?: FocusRequest | null;
}

// Half the rendered EntityNode card (w-[220px] × ~72px) — react-flow's setCenter
// targets a point, but node positions are top-left, so we offset to the centre.
const NODE_HALF_W = 110;
const NODE_HALF_H = 36;
// How long a citation-focused node stays highlighted before fading back.
const FOCUS_HIGHLIGHT_MS = 1800;

function TracerInner({
  trace,
  graphFocus,
  onToggleFocus,
  focusNode,
}: {
  trace: TraceState;
  graphFocus?: boolean;
  onToggleFocus?: () => void;
  focusNode?: FocusRequest | null;
}) {
  const { zoomIn, zoomOut, fitView, setCenter } = useReactFlow();
  // Default OFF: the canvas shows ONLY the traced execution path. Toggling this
  // on reveals the surrounding sub-graph (background context) for power users.
  const [showContext, setShowContext] = useState(false);

  // React Flow holds the live, draggable node/edge state. We seed it from the
  // dagre layout (see effect below) but never re-feed positions on every
  // render, so user drags stick. onNodesChange runs applyNodeChanges for us.
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  // How many nodes are background-only (not on the traced path) — surfaced on
  // the Context toggle so the user knows how much is being hidden.
  const hiddenCount = useMemo(
    () => trace.graph.nodes.filter((n) => !n.active).length,
    [trace]
  );

  // Build the rendered nodes/edges. By default we filter STRICTLY to the
  // execution path (`active`) so there's zero background noise — only the exact
  // nodes/edges the backend traversed for this query. The visible set is then
  // re-laid-out with dagre so its bounds are recalculated and it sits compact
  // and centered (instead of inheriting gaps from the full-graph layout).
  // Memoised on [trace, showContext], so it can't fight user drags on re-render.
  const computed = useMemo(() => {
    const visibleNodes = showContext
      ? trace.graph.nodes
      : trace.graph.nodes.filter((n) => n.active);
    const visibleIds = new Set(visibleNodes.map((n) => n.id));

    const visibleEdges = trace.graph.edges.filter(
      (e) =>
        (showContext || e.active) &&
        visibleIds.has(e.source) &&
        visibleIds.has(e.target)
    );

    // Recompute layout for ONLY the visible subgraph → tight, centered bounds.
    const laidOut = layoutGraph(visibleNodes, visibleEdges);

    const builtNodes: Node[] = laidOut.map((n) => ({
      id: n.id,
      type: "entity",
      position: n.position,
      data: n,
      draggable: true,
    }));
    const builtEdges: Edge[] = visibleEdges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      type: "traced",
      data: { active: e.active, confidence: e.confidence, relation: e.relation },
      zIndex: e.active ? 10 : 1,
      markerEnd: {
        type: MarkerType.ArrowClosed,
        // GRAPH-LEGIBILITY PASS — the arrowhead is a separate SVG marker, so it
        // must be dimmed in lockstep with the edge stroke (TracedEdge.tsx) or
        // non-active edges would fade but keep dark, prominent arrow tips. Active
        // stays indigo; non-active drops to a near-background grey + smaller head
        // so context arrows recede and the traced path's arrows lead the eye.
        width: e.active ? 16 : 11,
        height: e.active ? 16 : 11,
        color: e.active ? "#6366f1" : "#e4e4e7",
      },
    }));
    return { builtNodes, builtEdges };
  }, [trace, showContext]);

  // Seed positions from the dagre layout ONCE per graph load — i.e. on initial
  // mount, a new search (trace identity changes), or a context toggle. Because
  // `computed` is referentially stable between those events, this effect does
  // not re-run on ordinary re-renders, so dragged nodes are never snapped back.
  useEffect(() => {
    setNodes(computed.builtNodes);
    setEdges(computed.builtEdges);
    const t = setTimeout(() => fitView({ padding: 0.2, duration: 600 }), 140);
    return () => clearTimeout(t);
  }, [computed, setNodes, setEdges, fitView]);

  // --- Answer-citation focus ----------------------------------------------- //
  // Always read the LATEST nodes via a ref so focusById can stay referentially
  // stable (otherwise the focus effect would re-fire on every drag and yank the
  // viewport). `pendingFocus` defers a focus until a hidden node is revealed.
  const nodesRef = useRef(nodes);
  nodesRef.current = nodes;
  const pendingFocus = useRef<string | null>(null);
  const lastFocusNonce = useRef(-1);
  const highlightTimer = useRef<number | null>(null);

  const focusById = useRef((id: string): boolean => {
    const target = nodesRef.current.find((n) => n.id === id);
    if (!target) return false; // not currently rendered → caller handles reveal
    setCenter(
      target.position.x + NODE_HALF_W,
      target.position.y + NODE_HALF_H,
      { zoom: 1.3, duration: 600 }
    );
    // Mark it selected so EntityNode draws the focus ring; clear after a beat.
    setNodes((ns) => ns.map((n) => ({ ...n, selected: n.id === id })));
    if (highlightTimer.current) window.clearTimeout(highlightTimer.current);
    highlightTimer.current = window.setTimeout(() => {
      setNodes((ns) =>
        ns.some((n) => n.selected)
          ? ns.map((n) => (n.selected ? { ...n, selected: false } : n))
          : ns
      );
    }, FOCUS_HIGHLIGHT_MS);
    return true;
  }).current;

  // A new focus request (citation click): pan to it if rendered; otherwise
  // reveal context and queue it for the retry effect below. Nonce-gated so an
  // unrelated re-render (e.g. a fresh query) never re-focuses a stale citation.
  useEffect(() => {
    if (!focusNode || focusNode.nonce === lastFocusNonce.current) return;
    lastFocusNonce.current = focusNode.nonce;
    if (focusById(focusNode.id)) {
      pendingFocus.current = null;
      return;
    }
    if (trace.graph.nodes.some((n) => n.id === focusNode.id)) {
      pendingFocus.current = focusNode.id; // it exists but is hidden → reveal
      setShowContext(true);
    }
  }, [focusNode, focusById, trace.graph.nodes]);

  // Once the (possibly expanded) node set mounts, satisfy any queued focus.
  useEffect(() => {
    if (pendingFocus.current && focusById(pendingFocus.current)) {
      pendingFocus.current = null;
    }
  }, [nodes, focusById]);

  // Tidy the highlight timer on unmount.
  useEffect(
    () => () => {
      if (highlightTimer.current) window.clearTimeout(highlightTimer.current);
    },
    []
  );

  const tracedPath = trace.graph.nodes.filter((n) => n.active);

  return (
    <div className="relative h-full w-full">
      {/* Gradient + marker defs for the animated trace stroke */}
      <svg className="pointer-events-none absolute h-0 w-0">
        <defs>
          <linearGradient id="trace-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#6366f1" />
            <stop offset="100%" stopColor="#8b5cf6" />
          </linearGradient>
        </defs>
      </svg>

      {/* Trace summary strip */}
      <div className="pointer-events-none absolute left-4 top-4 z-20 max-w-[min(60%,520px)]">
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: "easeOut" }}
          className="pointer-events-auto rounded-xl border border-border bg-white/80 px-3.5 py-2.5 shadow-soft backdrop-blur"
        >
          <div className="flex items-center gap-2">
            <Route className="h-4 w-4 text-indigo-600" />
            <span className="text-xs font-semibold text-zinc-900">
              Traced Path
            </span>
            <Badge variant="indigo" className="gap-1">
              <Sparkles className="h-3 w-3" />
              {tracedPath.length} nodes
            </Badge>
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-1 font-mono text-[11px] text-zinc-500">
            {tracedPath.map((n, i) => (
              <span key={n.id} className="flex items-center gap-1">
                <span className="rounded bg-indigo-50 px-1.5 py-0.5 text-indigo-700">
                  {n.label}
                </span>
                {i < tracedPath.length - 1 && (
                  <span className="text-zinc-300">→</span>
                )}
              </span>
            ))}
          </div>
        </motion.div>
      </div>

      {/* Floating control pill */}
      <div className="absolute right-4 top-4 z-20">
        <GraphControls
          onZoomIn={() => zoomIn({ duration: 250 })}
          onZoomOut={() => zoomOut({ duration: 250 })}
          onRecenter={() => fitView({ padding: 0.2, duration: 500 })}
          showContext={showContext}
          hiddenCount={hiddenCount}
          graphFocus={graphFocus}
          onToggleFocus={onToggleFocus}
          onToggleContext={(v) => {
            setShowContext(v);
            toast(v ? "Showing surrounding context" : "Traced path only", {
              description: v
                ? `${hiddenCount} background node${hiddenCount === 1 ? "" : "s"} revealed`
                : "Canvas focused on the exact path the router traversed",
            });
          }}
        />
      </div>

      {/* Legend */}
      <div className="absolute bottom-4 left-4 z-20">
        <GraphLegend />
      </div>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.18 }}
        minZoom={0.4}
        maxZoom={1.8}
        proOptions={{ hideAttribution: true }}
        nodesDraggable
        nodesConnectable={false}
        elementsSelectable
        className="dotted-grid"
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={22}
          size={1.4}
          color="#e4e4e7"
        />
      </ReactFlow>
    </div>
  );
}

function TracerSkeleton() {
  return (
    <div className="dotted-grid relative h-full w-full p-6">
      <div className="absolute left-4 top-4">
        <Skeleton className="h-16 w-72 rounded-xl" />
      </div>
      <div className="absolute right-4 top-4">
        <Skeleton className="h-10 w-56 rounded-full" />
      </div>
      <div className="grid h-full place-items-center">
        <div className="relative h-72 w-full max-w-2xl">
          {[
            "left-0 top-24",
            "left-1/3 top-4",
            "left-1/3 top-44",
            "left-2/3 top-24",
            "right-0 top-10",
            "right-0 top-52",
          ].map((pos, i) => (
            <Skeleton
              key={i}
              className={`absolute ${pos} h-14 w-40 rounded-xl`}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

export function VisualTracer({
  trace,
  loading,
  graphFocus,
  onToggleFocus,
  focusNode,
}: VisualTracerProps) {
  if (loading) return <TracerSkeleton />;
  return (
    <ReactFlowProvider>
      <TracerInner
        trace={trace}
        graphFocus={graphFocus}
        onToggleFocus={onToggleFocus}
        focusNode={focusNode}
      />
    </ReactFlowProvider>
  );
}
