import { Waypoints } from "lucide-react";
import { cn } from "@/lib/utils";

/** TraceRAG wordmark — indigo glyph, with a coral LadybugDB attribution dot. */
export function Wordmark({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <div className="relative flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-node">
        <Waypoints className="h-4.5 w-4.5" strokeWidth={2.25} />
        {/* LadybugDB coral accent dot */}
        <span className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-white bg-rose-500" />
      </div>
      <div className="leading-none">
        <div className="flex items-baseline gap-1">
          <span className="text-[15px] font-bold tracking-tight text-zinc-900">
            TraceRAG
          </span>
          <span className="rounded bg-indigo-50 px-1 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wider text-indigo-600">
            Studio
          </span>
        </div>
        <span className="text-[10px] font-medium text-zinc-400">
          GraphRAG Observability ·{" "}
          <span className="text-rose-500">LadybugDB</span>
        </span>
      </div>
    </div>
  );
}
