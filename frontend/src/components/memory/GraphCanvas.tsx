import { useEffect, useMemo, useRef } from "react";
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
import { Maximize2, Minus, Plus } from "lucide-react";
import { MemoryNode, type MemoryNodeData } from "./MemoryNode";
import { layoutGraph } from "@/lib/layout";
import { cn } from "@/lib/utils";
import type { TraceNode, TraceState } from "@/types/trace";

const nodeTypes = { memory: MemoryNode };

// nonce lets clicking the same citation twice re-trigger the pan
export interface FocusRequest {
  id: string;
  nonce: number;
}

// node positions are top-left; offset by half the pill so setCenter is exact.
// NODE_HALF_W is coupled to w-[240px] in MemoryNode.tsx — keep them in sync.
const NODE_HALF_W = 120;
const NODE_HALF_H = 30;

// light neubrutalist canvas colors (mirrors --m-accent emerald)
const ACCENT = "#059669";
const MARKER_FAINT = "rgba(19,19,22,0.3)";
const DOTS = "rgba(19,19,22,0.14)";
const LIME = "#C8F169";

interface GraphCanvasProps {
  trace: TraceState;
  // true while a query runs — the canvas plays the "searching memory" animation
  // instead of a spinner; the previous graph stays visible underneath
  tracing: boolean;
  focusNode?: FocusRequest | null;
  onSelectNode?: (node: TraceNode | null) => void;
}

function CanvasInner({ trace, tracing, focusNode, onSelectNode }: GraphCanvasProps) {
  const { zoomIn, zoomOut, fitView, setCenter } = useReactFlow();
  const [nodes, setNodes, onNodesChange] = useNodesState<MemoryNodeData>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  const computed = useMemo(() => {
    const laidOut = layoutGraph(trace.graph.nodes, trace.graph.edges);
    const builtNodes: Node<MemoryNodeData>[] = laidOut.map((n, i) => ({
      id: n.id,
      type: "memory",
      position: n.position,
      data: { ...n, searching: tracing, searchDelayIndex: i },
      draggable: true,
    }));
    const builtEdges: Edge[] = trace.graph.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      className: e.active && !tracing ? "edge-traced" : undefined,
      zIndex: e.active ? 10 : 1,
      markerEnd: {
        type: MarkerType.ArrowClosed,
        width: e.active ? 15 : 11,
        height: e.active ? 15 : 11,
        color: e.active && !tracing ? ACCENT : MARKER_FAINT,
      },
    }));
    return { builtNodes, builtEdges };
  }, [trace, tracing]);

  // seed positions per graph load so user drags aren't snapped back mid-session
  useEffect(() => {
    setNodes(computed.builtNodes);
    setEdges(computed.builtEdges);
    const t = setTimeout(() => fitView({ padding: 0.25, duration: 700 }), 120);
    return () => clearTimeout(t);
  }, [computed, setNodes, setEdges, fitView]);

  // citation pan: smooth camera glide to the node, brief selection highlight
  const nodesRef = useRef(nodes);
  nodesRef.current = nodes;
  const lastNonce = useRef(-1);
  useEffect(() => {
    if (!focusNode || focusNode.nonce === lastNonce.current) return;
    lastNonce.current = focusNode.nonce;
    const target = nodesRef.current.find((n) => n.id === focusNode.id);
    if (!target) return;
    setCenter(target.position.x + NODE_HALF_W, target.position.y + NODE_HALF_H, {
      zoom: 1.25,
      duration: 650,
    });
    setNodes((ns) => ns.map((n) => ({ ...n, selected: n.id === focusNode.id })));
  }, [focusNode, setCenter, setNodes]);

  const empty = trace.graph.nodes.length === 0;

  return (
    <div className="relative h-full w-full overflow-hidden">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        onNodeClick={(_, n) => onSelectNode?.(n.data as TraceNode)}
        onPaneClick={() => onSelectNode?.(null)}
        fitView
        fitViewOptions={{ padding: 0.25 }}
        minZoom={0.35}
        maxZoom={1.8}
        proOptions={{ hideAttribution: true }}
        nodesDraggable
        nodesConnectable={false}
        elementsSelectable
        className="memory-flow dotted-grid-dark"
      >
        <Background variant={BackgroundVariant.Dots} gap={26} size={1.3} color={DOTS} />
      </ReactFlow>

      {/* tracing sweep — a light beam pans across the canvas while searching */}
      {tracing && (
        <div className="pointer-events-none absolute inset-0 z-10 overflow-hidden">
          <div className="h-full w-40 animate-scan bg-gradient-to-r from-transparent via-emerald-500/10 to-transparent" />
        </div>
      )}

      {/* status chip — replaces any spinner; hard-shadow sticker */}
      {tracing && (
        <div className="pointer-events-none absolute left-1/2 top-6 z-20 -translate-x-1/2">
          <div className="flex items-center gap-2.5 rounded-full border border-[#131316] bg-white px-4 py-2 shadow-[2px_3px_0_0_#131316]">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-500 opacity-60" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
            </span>
            <span className="font-mono text-[11px] font-bold tracking-wide text-[#131316]">
              traversing graph…
            </span>
          </div>
        </div>
      )}

      {/* idle hero — landing-page voice: Space Grotesk + lime marker */}
      {empty && !tracing && (
        <div className="pointer-events-none absolute inset-0 grid place-items-center">
          <div className="max-w-xl px-8 text-center">
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.4em] text-zinc-400">
              {"Graphsight · Memory"}
            </p>
            <h1 className="mt-4 font-display text-4xl font-bold leading-[1.12] tracking-tight text-[#131316]">
              Your codebase remembers{" "}
              <span
                className="inline-block -rotate-1 rounded-lg px-2"
                style={{ backgroundColor: LIME }}
              >
                everything.
              </span>
            </h1>
            <p className="mx-auto mt-4 max-w-sm text-sm leading-relaxed text-zinc-600">
              Trace any bug to the PR that shipped it, the person who wrote it,
              and the ticket that asked for it.
            </p>
            <p className="mt-8 flex items-center justify-center gap-2 text-xs text-zinc-500">
              <kbd className="rounded-md border border-[#131316] bg-white px-2 py-1 font-mono text-[11px] font-bold text-[#131316] shadow-[2px_2px_0_0_#131316]">
                ⌘K
              </kbd>
              to start a trace
            </p>
          </div>
        </div>
      )}

      {/* zoom cluster — hard-shadow card, bottom right */}
      <div className="absolute bottom-5 right-5 z-20 flex flex-col overflow-hidden rounded-lg border border-[#131316] bg-white shadow-[2px_3px_0_0_#131316]">
        <CanvasButton label="Zoom in" onClick={() => zoomIn({ duration: 200 })}>
          <Plus className="h-3.5 w-3.5" />
        </CanvasButton>
        <CanvasButton label="Zoom out" onClick={() => zoomOut({ duration: 200 })}>
          <Minus className="h-3.5 w-3.5" />
        </CanvasButton>
        <CanvasButton
          label="Fit view"
          onClick={() => fitView({ padding: 0.25, duration: 500 })}
        >
          <Maximize2 className="h-3.5 w-3.5" />
        </CanvasButton>
      </div>
    </div>
  );
}

function CanvasButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className={cn(
        "flex h-9 w-9 items-center justify-center border-b border-zinc-200 text-zinc-600 last:border-b-0",
        "transition-colors duration-150 hover:bg-zinc-100 hover:text-[#131316]"
      )}
    >
      {children}
    </button>
  );
}

export function GraphCanvas(props: GraphCanvasProps) {
  return (
    <ReactFlowProvider>
      <CanvasInner {...props} />
    </ReactFlowProvider>
  );
}
