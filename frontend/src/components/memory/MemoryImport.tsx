import { useCallback, useEffect, useState, type ChangeEvent, type DragEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { FileJson, GitCompareArrows, Upload } from "lucide-react";
import { AppLayout } from "./AppLayout";
import { RunDiff } from "./RunDiff";
import { cn } from "@/lib/utils";
import type { TraceState } from "@/types/trace";

const LIME = "#C8F169";

/** one entry in a served history directory (graphsight .graphsight/) */
interface RunEntry {
  file: string;
  query?: string;
  computedAt?: string;
  nodes?: number;
}

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
  const runsSrc = searchParams.get("runs");
  const [runs, setRuns] = useState<RunEntry[] | null>(null);
  const [fetching, setFetching] = useState(Boolean(src || runsSrc));
  const [picked, setPicked] = useState<string[]>([]);
  const [diff, setDiff] = useState<{
    a: { label: string; trace: TraceState };
    b: { label: string; trace: TraceState };
  } | null>(null);

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

  // ?runs=<url> — a history directory served by the CLI; show the run list
  useEffect(() => {
    if (!runsSrc) return;
    setFetching(true);
    fetch(runsSrc)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status} fetching the run list`);
        return res.json() as Promise<RunEntry[]>;
      })
      .then(setRuns)
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Could not fetch the run list.")
      )
      .finally(() => setFetching(false));
  }, [runsSrc]);

  const fetchRun = useCallback(async (file: string): Promise<TraceState> => {
    const res = await fetch(`/__run__/${encodeURIComponent(file)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status} fetching ${file}`);
    return parseTraceState(await res.text());
  }, []);

  const openRun = useCallback(
    (file: string) => {
      setFetching(true);
      fetchRun(file)
        .then((t) => {
          setTrace(t);
          setError(null);
        })
        .catch((err) =>
          setError(err instanceof Error ? err.message : `Could not fetch ${file}.`)
        )
        .finally(() => setFetching(false));
    },
    [fetchRun]
  );

  const togglePick = useCallback((file: string) => {
    setPicked((prev) =>
      prev.includes(file) ? prev.filter((f) => f !== file) : [...prev.slice(-1), file]
    );
  }, []);

  const compare = useCallback(() => {
    if (picked.length !== 2) return;
    setFetching(true);
    Promise.all(picked.map(fetchRun))
      .then(([ta, tb]) => {
        setDiff({
          a: { label: picked[0], trace: ta },
          b: { label: picked[1], trace: tb },
        });
        setError(null);
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Could not load both runs.")
      )
      .finally(() => setFetching(false));
  }, [picked, fetchRun]);

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

  if (diff) {
    return (
      <RunDiff
        a={diff.a}
        b={diff.b}
        onBack={() => setDiff(null)}
        onOpen={(t) => setTrace(t)}
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

  if (runs) {
    return (
      <div className="m-light flex min-h-dvh flex-col items-center bg-paper px-5 py-14 font-sans antialiased">
        <div className="w-full max-w-xl">
          <p className="text-center font-mono text-[10px] font-bold uppercase tracking-[0.4em] text-zinc-400">
            Graphsight · Run history
          </p>
          <h1 className="mt-3 text-center font-display text-3xl font-bold tracking-tight text-[#131316]">
            Every run,{" "}
            <span className="inline-block -rotate-1 rounded-lg px-2" style={{ backgroundColor: LIME }}>
              on record
            </span>
          </h1>
          <p className="mt-3 text-center text-sm text-zinc-600">
            {runs.length} trace{runs.length === 1 ? "" : "s"} in this history — click one to open it.
          </p>

          {runs.length >= 2 && (
            <div className="mt-6 flex items-center justify-between rounded-xl border border-[#131316] bg-white px-4 py-2.5 shadow-[2px_3px_0_0_#131316]">
              <p className="text-[12.5px] font-medium text-zinc-600">
                {picked.length === 2
                  ? "Two runs selected — see what changed in retrieval."
                  : "Tick two runs to compare them."}
              </p>
              <button
                type="button"
                onClick={compare}
                disabled={picked.length !== 2}
                className={cn(
                  "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-bold",
                  picked.length === 2
                    ? "bg-[#131316] text-white shadow-[2px_3px_0_0_#C8F169]"
                    : "cursor-not-allowed bg-zinc-100 text-zinc-400"
                )}
              >
                <GitCompareArrows className="h-4 w-4" />
                Compare
              </button>
            </div>
          )}

          <div className="mt-4 flex flex-col gap-3">
            {runs.map((run) => (
              <div
                key={run.file}
                className={cn(
                  "flex items-center gap-3 rounded-xl border border-[#131316] bg-white p-4 shadow-[3px_4px_0_0_#131316]",
                  "transition-transform duration-150 hover:-translate-y-0.5"
                )}
              >
                <input
                  type="checkbox"
                  aria-label={`select ${run.query || run.file} for comparison`}
                  checked={picked.includes(run.file)}
                  onChange={() => togglePick(run.file)}
                  className="h-4 w-4 shrink-0 accent-[#059669]"
                />
                <button
                  type="button"
                  onClick={() => openRun(run.file)}
                  className="min-w-0 flex-1 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#059669]"
                >
                  <p className="truncate text-[14px] font-bold leading-snug text-[#131316]">
                    {run.query || run.file}
                  </p>
                  <p className="mt-1.5 font-mono text-[11px] text-zinc-500">
                    {run.computedAt ? new Date(run.computedAt).toLocaleString() : "—"}
                    {typeof run.nodes === "number" && (
                      <>
                        {" · "}
                        <span className="font-bold text-emerald-700">{run.nodes} nodes</span>
                      </>
                    )}
                  </p>
                </button>
              </div>
            ))}
            {runs.length === 0 && (
              <p className="text-center text-sm text-zinc-500">
                No traces here yet — run your agent with{" "}
                <code className="font-mono text-[12px] font-bold">capture(tracer, …)</code> first.
              </p>
            )}
          </div>

          {error && (
            <p className="mt-5 flex items-center justify-center gap-2 text-center text-[13px] font-medium text-red-500">
              <FileJson className="h-4 w-4 shrink-0" />
              {error}
            </p>
          )}
        </div>
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
          <Link to="/memory/preview" className="font-bold text-emerald-700 hover:underline">
            see the live demo
          </Link>
        </p>
      </div>
    </div>
  );
}
