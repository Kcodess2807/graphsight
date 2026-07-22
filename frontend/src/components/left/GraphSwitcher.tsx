import { useEffect, useState } from "react";
import { Database } from "lucide-react";
import { toast } from "sonner";
import { listGraphs, switchGraph, type GraphInfo } from "@/lib/api";

const STORAGE_KEY = "graphsight.activeGraph";

// localStorage access can throw (private mode, disabled storage), so every
// read/write is guarded — persistence is a nicety and must never break the UI.
function readSavedGraph(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}
function writeSavedGraph(id: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, id);
  } catch {
    /* ignore */
  }
}
function clearSavedGraph(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

// dropdown to hot-swap the active graph without a server restart
export function GraphSwitcher({ onSwitched }: { onSwitched?: () => void }) {
  const [graphs, setGraphs] = useState<GraphInfo[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Mount-only reconcile. We read localStorage and (if needed) re-assert the
  // saved graph HERE, inside the one-shot mount effect — NOT in an effect that
  // depends on `active`. That's what prevents the feedback loop: re-asserting
  // changes `active`, and if this watched `active` it would re-fire forever.
  useEffect(() => {
    let cancelled = false;
    listGraphs()
      .then(async (r) => {
        if (cancelled) return;
        setGraphs(r.graphs);

        const saved = readSavedGraph();
        // validate against the freshly-fetched list: the saved graph file may
        // have been deleted since we last stored it.
        const savedIsValid = !!saved && r.graphs.some((g) => g.id === saved);

        if (saved && savedIsValid && saved !== r.active) {
          // Durable restore across server restarts: the server reset to its
          // default, but the user previously chose `saved`. Re-assert it.
          // Silent (no toast); onSwitched refreshes suggestions for the graph.
          try {
            const res = await switchGraph(saved);
            if (cancelled) return;
            setActive(res.active);
            setGraphs((gs) =>
              gs.map((g) => ({ ...g, active: g.id === res.active }))
            );
            onSwitched?.();
            return;
          } catch (err) {
            console.error("[Graphsight] restore saved graph failed:", err);
            // fall through to adopt the server's active graph
          }
        }

        // saved value is stale (graph gone) -> drop it so it stops being tried
        if (saved && !savedIsValid) clearSavedGraph();

        setActive(r.active);
      })
      .catch((err) => console.error("[Graphsight] listGraphs failed:", err));
    return () => {
      cancelled = true;
    };
    // run once on mount; onSwitched is stable enough not to warrant re-running
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (graphs.length <= 1) return null; // nothing to switch between

  const onChange = async (id: string) => {
    if (id === active || busy) return;
    setBusy(true);
    const toastId = toast.loading("Switching graph…");
    try {
      const res = await switchGraph(id);
      setActive(res.active);
      setGraphs((gs) => gs.map((g) => ({ ...g, active: g.id === res.active })));
      writeSavedGraph(res.active); // remember the choice across reloads / restarts
      toast.success(`Switched to ${res.label}`, {
        id: toastId,
        description: `${res.nodes} nodes loaded`,
      });
      onSwitched?.();
    } catch (err) {
      toast.error("Could not switch graph", {
        id: toastId,
        description: String(err),
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <label className="flex items-center gap-2" title="Active graph">
      <Database className="h-4 w-4 shrink-0 text-zinc-400" />
      <select
        value={active ?? ""}
        disabled={busy}
        onChange={(e) => onChange(e.target.value)}
        aria-label="Active graph"
        className="w-full cursor-pointer rounded-lg border border-border bg-card px-2.5 py-1.5 text-xs font-medium text-zinc-700 shadow-soft transition-colors hover:border-zinc-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"
      >
        {graphs.map((g) => (
          <option key={g.id} value={g.id}>
            {g.label}
          </option>
        ))}
      </select>
    </label>
  );
}
