import { useEffect, useState } from "react";
import { Database } from "lucide-react";
import { toast } from "sonner";
import { listGraphs, switchGraph, type GraphInfo } from "@/lib/api";

// dropdown to hot-swap the active graph without a server restart
export function GraphSwitcher({ onSwitched }: { onSwitched?: () => void }) {
  const [graphs, setGraphs] = useState<GraphInfo[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    listGraphs()
      .then((r) => {
        setGraphs(r.graphs);
        setActive(r.active);
      })
      .catch((err) => console.error("[TraceRAG] listGraphs failed:", err));
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
