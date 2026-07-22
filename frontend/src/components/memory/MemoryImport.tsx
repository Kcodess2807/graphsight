import { useCallback, useEffect, useState, type ChangeEvent, type DragEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { FileJson, Upload } from "lucide-react";
import { AppLayout } from "./AppLayout";
import { cn } from "@/lib/utils";
import type { TraceState } from "@/types/trace";

const LIME = "#C8F169";

/** minimal structural check — enough to render without crashing */
function parseTraceState(raw: string): TraceState {
  const data = JSON.parse(raw) as TraceState;
  if (typeof data?.query !== "string" || !data?.graph || !Array.isArray(data.graph.nodes)) {
    throw new Error("Not a TraceState: expected { query, graph: { nodes, edges }, … }");
  }
  data.graph.edges = Array.isArray(data.graph.edges) ? data.graph.edges : [];
  data.steps = Array.isArray(data.steps) ? data.steps : [];
  data.metrics = data.metrics ?? { queryTimeSec: 0 };
  return data;
}

/**
 * Render an external trace (e.g. from graphsight-langgraph's to_tracestate)
 * in the full Studio — drop or paste the JSON, no backend involved.
 */
export function MemoryImport() {
  const [trace, setTrace] = useState<TraceState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [searchParams] = useSearchParams();
  const src = searchParams.get("src");
  const [fetching, setFetching] = useState(Boolean(src));

  const load = useCallback((raw: string) => {
    try {
      setTrace(parseTraceState(raw));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not parse that JSON.");
    }
  }, []);

  // ?src=<url> auto-loads a trace — used by the graphsight CLI, which
  // serves the given file and opens the browser here
  useEffect(() => {
    if (!src) return;
    setFetching(true);
    fetch(src)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status} fetching ${src}`);
        return res.text();
      })
      .then(load)
      .catch((err) =>
        setError(err instanceof Error ? err.message : `Could not fetch ${src}.`)
      )
      .finally(() => setFetching(false));
  }, [src, load]);

  const onFile = useCallback(
    (file: File | undefined) => {
      if (!file) return;
      file.text().then(load, () => setError("Could not read that file."));
    },
    [load]
  );

  const onDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault();
      setDragging(false);
      onFile(e.dataTransfer.files?.[0]);
    },
    [onFile]
  );

  const onPick = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => onFile(e.target.files?.[0] ?? undefined),
    [onFile]
  );

  if (trace) {
    return (
      <AppLayout
        trace={trace}
        tracing={false}
        answer={null}
        suggestions={[]}
        recentQueries={[]}
        onQuery={() => {
          /* imported traces are static — no live backend behind this view */
        }}
        onNewChat={() => setTrace(null)}
      />
    );
  }

  if (fetching) {
    return (
      <div className="m-light flex min-h-dvh items-center justify-center bg-paper font-sans antialiased">
        <p className="font-mono text-[11px] font-bold uppercase tracking-[0.4em] text-zinc-400">
          loading trace…
        </p>
      </div>
    );
  }

  return (
    <div className="m-light flex min-h-dvh flex-col items-center justify-center bg-paper px-5 font-sans antialiased">
      <div className="w-full max-w-lg">
        <p className="text-center font-mono text-[10px] font-bold uppercase tracking-[0.4em] text-zinc-400">
          Graphsight · Import
        </p>
        <h1 className="mt-3 text-center font-display text-3xl font-bold tracking-tight text-[#131316]">
          Render an{" "}
          <span className="inline-block -rotate-1 rounded-lg px-2" style={{ backgroundColor: LIME }}>
            external trace
          </span>
        </h1>
        <p className="mx-auto mt-3 max-w-sm text-center text-sm leading-relaxed text-zinc-600">
          Drop a <code className="font-mono text-[12px] font-bold">trace_state.json</code> produced
          by <code className="font-mono text-[12px] font-bold">graphsight-langgraph</code> — the full
          Studio renders it, no backend needed.
        </p>

        <label
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={cn(
            "mt-8 flex cursor-pointer flex-col items-center gap-3 rounded-xl border-2 border-dashed px-6 py-12",
            "transition-colors duration-150",
            dragging
              ? "border-emerald-600 bg-emerald-50"
              : "border-[#131316] bg-white hover:bg-zinc-50"
          )}
        >
          <span className="flex h-11 w-11 items-center justify-center rounded-xl border border-[#131316] bg-white shadow-[2px_3px_0_0_#131316]">
            <Upload className="h-5 w-5 text-[#131316]" strokeWidth={2.25} />
          </span>
          <span className="text-sm font-bold text-[#131316]">
            Drop the JSON here, or click to browse
          </span>
          <input type="file" accept=".json,application/json" onChange={onPick} className="sr-only" />
        </label>

        <details className="mt-4">
          <summary className="cursor-pointer text-center text-xs font-medium text-zinc-500 hover:text-[#131316]">
            …or paste JSON
          </summary>
          <textarea
            rows={6}
            spellCheck={false}
            placeholder='{"query": "...", "graph": {"nodes": [...], "edges": [...]}, ...}'
            onChange={(e) => e.target.value.trim() && load(e.target.value)}
            className={cn(
              "mt-2 w-full rounded-xl border border-[#131316] bg-white p-3 font-mono text-[11px] text-[#131316]",
              "placeholder:text-zinc-400 focus:outline-none focus:shadow-[3px_4px_0_0_#059669]"
            )}
          />
        </details>

        {error && (
          <p className="mt-4 flex items-center justify-center gap-2 text-center text-[13px] font-medium text-red-500">
            <FileJson className="h-4 w-4 shrink-0" />
            {error}
          </p>
        )}

        <p className="mt-8 text-center text-xs text-zinc-500">
          Generate one:{" "}
          <code className="font-mono text-[11px] font-bold text-[#131316]">
            python example/demo_agent.py
          </code>{" "}
          in <code className="font-mono text-[11px] font-bold">graphsight-langgraph/</code> ·{" "}
          <Link to="/studio" className="font-bold text-emerald-700 hover:underline">
            back to Studio
          </Link>
        </p>
      </div>
    </div>
  );
}
