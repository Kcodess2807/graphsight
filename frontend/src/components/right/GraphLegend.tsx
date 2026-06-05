import { ENTITY_STYLES } from "@/lib/entity";
import type { EntityType } from "@/types/trace";

const LEGEND_TYPES: EntityType[] = [
  "PR",
  "Service",
  "Person",
  "Library",
  "Ticket",
  "Tool",
];

export function GraphLegend() {
  return (
    <div className="glass rounded-xl border border-white/60 px-3 py-2.5 shadow-soft ring-1 ring-black/[0.03]">
      <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
        Entity types
      </p>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
        {LEGEND_TYPES.map((type) => {
          const s = ENTITY_STYLES[type];
          const Icon = s.icon;
          return (
            <div key={type} className="flex items-center gap-1.5">
              <span
                className={`flex h-4 w-4 items-center justify-center rounded border ${s.chip}`}
              >
                <Icon className={`h-2.5 w-2.5 ${s.iconColor}`} />
              </span>
              <span className="text-[11px] font-medium text-zinc-600">
                {type}
              </span>
            </div>
          );
        })}
      </div>
      <div className="mt-2.5 flex items-center gap-1.5 border-t border-zinc-200/70 pt-2">
        <span className="h-0.5 w-5 rounded-full bg-gradient-to-r from-indigo-500 to-violet-500" />
        <span className="text-[11px] font-medium text-zinc-600">
          Active trace
        </span>
      </div>
    </div>
  );
}
