import { ArrowUpRight } from "lucide-react";
import { ENTITY_STYLES } from "@/lib/entity";
import { cn } from "@/lib/utils";
import type { EntityType } from "@/types/trace";
import type { Suggestion } from "@/lib/api";

export function SuggestionChips({
  suggestions,
  onPick,
}: {
  suggestions: Suggestion[];
  onPick: (query: string) => void;
}) {
  if (suggestions.length === 0) return null;

  return (
    <div className="flex flex-col gap-1.5">
      {suggestions.map((s) => {
        // backend type is a free string, fall back if it's not a known EntityType
        const style = ENTITY_STYLES[s.type as EntityType];
        const Icon = style?.icon;
        return (
          <button
            key={s.query}
            type="button"
            onClick={() => onPick(s.query)}
            className="group flex items-center gap-2.5 rounded-lg border border-border bg-card px-3 py-2 text-left shadow-soft transition-colors hover:border-indigo-200 hover:bg-indigo-50/50"
          >
            {Icon && (
              <span
                className={cn(
                  "flex h-6 w-6 shrink-0 items-center justify-center rounded-md border",
                  style.chip
                )}
              >
                <Icon className={cn("h-3.5 w-3.5", style.iconColor)} />
              </span>
            )}
            <span className="line-clamp-1 flex-1 text-[13px] text-zinc-700 group-hover:text-zinc-900">
              {s.query}
            </span>
            <ArrowUpRight className="h-3.5 w-3.5 shrink-0 text-zinc-300 transition-colors group-hover:text-indigo-500" />
          </button>
        );
      })}
    </div>
  );
}
