import { ArrowLeft, ArrowRight, Minus, Plus } from "lucide-react";
import { MEMORY_ENTITY_STYLES } from "./entityTheme";
import { cn } from "@/lib/utils";
import type { TraceState, TraceNode } from "@/types/trace";

const LIME = "#C8F169";

interface RunDiffProps {
  a: { label: string; trace: TraceState };
  b: { label: string; trace: TraceState };
  onBack: () => void;
  onOpen: (trace: TraceState) => void;
}

interface NodeDelta {
  node: TraceNode;
  other?: TraceNode;
  change: "added" | "removed" | "kept";
}

/* diff keyed by node id: what B retrieved that A didn't, and vice versa */
function diffNodes(a: TraceState, b: TraceState): NodeDelta[] {
  const aById = new Map(a.graph.nodes.map((n) => [n.id, n]));
  const bById = new Map(b.graph.nodes.map((n) => [n.id, n]));
  const out: NodeDelta[] = [];
  for (const n of a.graph.nodes) {
    out.push(
      bById.has(n.id)
        ? { node: n, other: bById.get(n.id), change: "kept" }
        : { node: n, change: "removed" }
    );
  }
  for (const n of b.graph.nodes) {
    if (!aById.has(n.id)) out.push({ node: n, change: "added" });
  }
  return out;
}

function fmtScore(s: number | null | undefined) {
  return s == null ? "—" : s.toFixed(2);
}

function usage(n: TraceNode) {
  return n.active ? "used" : "unused";
}

function NodeRow({ delta }: { delta: NodeDelta }) {
  const { node, other, change } = delta;
  const style = MEMORY_ENTITY_STYLES[node.type];
  const Icon = style.icon;
  const scoreChanged = other && fmtScore(node.score) !== fmtScore(other.score);
  const usageChanged = other && node.active !== other.active;

  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-xl border bg-white px-3.5 py-2.5",
        change === "kept"
          ? "border-zinc-300 shadow-[2px_3px_0_0_rgba(19,19,22,0.12)]"
          : "border-[#131316] shadow-[2px_3px_0_0_#131316]"
      )}
    >
      <span className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border", style.well)}>
        <Icon className={cn("h-4 w-4", style.glyph)} strokeWidth={2.25} />
      </span>

      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] font-bold text-[#131316]">{node.label}</p>
        <p className="font-mono text-[9.5px] uppercase tracking-[0.15em] text-zinc-400">{style.label}</p>
      </div>

      {change === "kept" && other ? (
        <div className="flex shrink-0 items-center gap-2 font-mono text-[11px]">
          <span className={cn(scoreChanged ? "font-bold text-[#131316]" : "text-zinc-500")}>
            {fmtScore(node.score)} → {fmtScore(other.score)}
          </span>
          <span
            className={cn(
              "rounded-full border px-2 py-0.5 text-[10px] font-bold",
              usageChanged ? "border-[#131316] text-[#131316]" : "border-zinc-300 text-zinc-400"
            )}
            style={usageChanged ? { backgroundColor: LIME } : undefined}
          >
            {usage(node)} → {other && usage(other)}
          </span>
        </div>
      ) : (
        <span
          className={cn(
            "flex shrink-0 items-center gap-1 rounded-full border border-[#131316] px-2 py-0.5 font-mono text-[10px] font-bold text-[#131316]",
            change === "added" ? "bg-emerald-100" : "bg-red-100"
          )}
        >
          {change === "added" ? <Plus className="h-3 w-3" /> : <Minus className="h-3 w-3" />}
          {change === "added" ? "only in B" : "only in A"}
        </span>
      )}
    </div>
  );
}

function RunCard({
  tag, label, trace, onOpen,
}: { tag: string; label: string; trace: TraceState; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex-1 rounded-xl border border-[#131316] bg-white p-4 text-left shadow-[3px_4px_0_0_#131316] transition-transform duration-150 hover:-translate-y-0.5"
    >
      <p className="font-mono text-[10px] font-bold uppercase tracking-[0.3em] text-zinc-400">
        run {tag}
      </p>
      <p className="mt-1 text-[13.5px] font-bold leading-snug text-[#131316]">{trace.query}</p>
      <p className="mt-1.5 font-mono text-[10.5px] text-zinc-500">
        {label} · {trace.graph.nodes.length} nodes · {trace.graph.edges.length} edges ·{" "}
        {trace.metrics.queryTimeSec}s
      </p>
    </button>
  );
}

export function RunDiff({ a, b, onBack, onOpen }: RunDiffProps) {
  const deltas = diffNodes(a.trace, b.trace);
  const added = deltas.filter((d) => d.change === "added");
  const removed = deltas.filter((d) => d.change === "removed");
  const kept = deltas.filter((d) => d.change === "kept");
  const changed = kept.filter(
    (d) => d.other && (fmtScore(d.node.score) !== fmtScore(d.other.score) || d.node.active !== d.other.active)
  );

  return (
    <div className="m-light min-h-dvh bg-paper px-5 py-10 font-sans antialiased">
      <div className="mx-auto max-w-2xl">
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-1.5 text-sm font-bold text-zinc-500 hover:text-[#131316]"
        >
          <ArrowLeft className="h-4 w-4" /> run history
        </button>

        <h1 className="mt-4 font-display text-2xl font-bold tracking-tight text-[#131316]">
          What changed in{" "}
          <span className="inline-block -rotate-1 rounded-lg px-2" style={{ backgroundColor: LIME }}>
            retrieval
          </span>
        </h1>
        <p className="mt-2 text-sm text-zinc-600">
          {added.length} retrieved only in B · {removed.length} only in A · {changed.length} of{" "}
          {kept.length} shared items changed score or usage. Click a run card to open it fully.
        </p>

        <div className="mt-6 flex flex-col gap-3 sm:flex-row">
          <RunCard tag="A" label={a.label} trace={a.trace} onOpen={() => onOpen(a.trace)} />
          <span className="hidden items-center sm:flex">
            <ArrowRight className="h-5 w-5 text-zinc-400" />
          </span>
          <RunCard tag="B" label={b.label} trace={b.trace} onOpen={() => onOpen(b.trace)} />
        </div>

        {removed.length > 0 && (
          <section className="mt-8">
            <h2 className="font-mono text-[11px] font-bold uppercase tracking-[0.25em] text-zinc-400">
              retrieved only in A
            </h2>
            <div className="mt-3 flex flex-col gap-2">
              {removed.map((d) => <NodeRow key={`a-${d.node.id}`} delta={d} />)}
            </div>
          </section>
        )}

        {added.length > 0 && (
          <section className="mt-8">
            <h2 className="font-mono text-[11px] font-bold uppercase tracking-[0.25em] text-zinc-400">
              retrieved only in B
            </h2>
            <div className="mt-3 flex flex-col gap-2">
              {added.map((d) => <NodeRow key={`b-${d.node.id}`} delta={d} />)}
            </div>
          </section>
        )}

        <section className="mt-8">
          <h2 className="font-mono text-[11px] font-bold uppercase tracking-[0.25em] text-zinc-400">
            in both — score A → B · usage A → B
          </h2>
          <div className="mt-3 flex flex-col gap-2">
            {kept.map((d) => <NodeRow key={`k-${d.node.id}`} delta={d} />)}
            {kept.length === 0 && (
              <p className="text-sm text-zinc-500">No overlap — the two runs retrieved entirely different items.</p>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
