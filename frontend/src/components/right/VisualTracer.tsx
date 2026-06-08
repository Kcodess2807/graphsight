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

// nonce lets clicking the same citation twice re-trigger the pan
export interface FocusRequest {
  id: string;
  nonce: number;
}

interface VisualTracerProps {
  trace: TraceState;
  loading: boolean;
  // full-graph focus, owned by TraceDashboard; optional so mobile can omit it
  graphFocus?: boolean;
  onToggleFocus?: () => void;
  focusNode?: FocusRequest | null;
}

// node positions are top-left; offset by half the card to center setCenter
const NODE_HALF_W = 110;
const NODE_HALF_H = 36;
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
  // off by default: show only the traced path, toggle reveals the sub-graph
  const [showContext, setShowContext] = useState(false);

  // seeded once from the dagre layout (effect below) so user drags stick
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  const hiddenCount = useMemo(
    () => trace.graph.nodes.filter((n) => !n.active).length,
    [trace]
  );

  // build visible nodes/edges, re-laid-out with dagre for tight centered bounds
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
        // dim the arrowhead in lockstep with the edge stroke in TracedEdge.tsx
        width: e.active ? 16 : 11,
        height: e.active ? 16 : 11,
        color: e.active ? "#6366f1" : "#e4e4e7",
      },
    }));
    return { builtNodes, builtEdges };
  }, [trace, showContext]);

  // seed positions once per graph load so dragged nodes aren't snapped back
  useEffect(() => {
    setNodes(computed.builtNodes);
    setEdges(computed.builtEdges);
    const t = setTimeout(() => fitView({ padding: 0.2, duration: 600 }), 140);
    return () => clearTimeout(t);
  }, [computed, setNodes, setEdges, fitView]);

  // read latest nodes via a ref so focusById stays stable and doesn't refire on drag
  const nodesRef = useRef(nodes);
  nodesRef.current = nodes;
  const pendingFocus = useRef<string | null>(null);
  const lastFocusNonce = useRef(-1);
  const highlightTimer = useRef<number | null>(null);

  const focusById = useRef((id: string): boolean => {
    const target = nodesRef.current.find((n) => n.id === id);
    if (!target) return false; // not rendered, caller handles reveal
    setCenter(
      target.position.x + NODE_HALF_W,
      target.position.y + NODE_HALF_H,
      { zoom: 1.3, duration: 600 }
    );
    // mark selected so EntityNode draws the focus ring, cleared after a beat
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

  // pan to a clicked citation if rendered, else reveal context and queue it
  useEffect(() => {
    if (!focusNode || focusNode.nonce === lastFocusNonce.current) return;
    lastFocusNonce.current = focusNode.nonce;
    if (focusById(focusNode.id)) {
      pendingFocus.current = null;
      return;
    }
    if (trace.graph.nodes.some((n) => n.id === focusNode.id)) {
      pendingFocus.current = focusNode.id; // exists but hidden, reveal it
      setShowContext(true);
    }
  }, [focusNode, focusById, trace.graph.nodes]);

  // satisfy any queued focus once the expanded node set mounts
  useEffect(() => {
    if (pendingFocus.current && focusById(pendingFocus.current)) {
      pendingFocus.current = null;
    }
  }, [nodes, focusById]);

  // clear the highlight timer on unmount
  useEffect(
    () => () => {
      if (highlightTimer.current) window.clearTimeout(highlightTimer.current);
    },
    []
  );

  const tracedPath = trace.graph.nodes.filter((n) => n.active);

  return (
    <div className="relative h-full w-full">
      {/* gradient defs for the animated trace stroke */}
      <svg className="pointer-events-none absolute h-0 w-0">
        <defs>
          <linearGradient id="trace-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#6366f1" />
            <stop offset="100%" stopColor="#8b5cf6" />
          </linearGradient>
        </defs>
      </svg>

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
