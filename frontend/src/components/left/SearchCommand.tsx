import { useEffect, useState } from "react";
import { Search, History, Sparkles, CornerDownLeft, GitBranch } from "lucide-react";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandShortcut,
} from "@/components/ui/command";
import { Badge } from "@/components/ui/badge";
import { QUERY_PRESETS } from "@/data/mockTrace";

interface SearchCommandProps {
  query: string;
  onQueryChange: (q: string) => void;
}

/**
 * The always-visible search input (styled cmdk) that opens a ⌘K command
 * palette overlay for query history and presets.
 */
export function SearchCommand({ query, onQueryChange }: SearchCommandProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);

  const select = (value: string) => {
    const q = value.trim();
    if (!q) return;
    onQueryChange(q);
    setOpen(false);
    setSearch("");
  };

  const typed = search.trim();

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Search traces — open command palette"
        className="group flex w-full items-center gap-2.5 rounded-xl border border-border bg-card px-3 py-2.5 text-left shadow-soft transition-colors hover:border-zinc-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <Search className="h-4 w-4 shrink-0 text-zinc-400 transition-colors group-hover:text-zinc-500" />
        <span className="line-clamp-1 flex-1 truncate text-sm text-zinc-600">
          {query}
        </span>
        <kbd className="hidden shrink-0 items-center gap-0.5 rounded-md border border-border bg-secondary px-1.5 py-0.5 font-mono text-[10px] font-medium text-zinc-500 sm:inline-flex">
          ⌘K
        </kbd>
      </button>

      <CommandDialog open={open} onOpenChange={setOpen}>
        <CommandInput
          value={search}
          onValueChange={setSearch}
          placeholder="Trace any query, recall history, or run a preset…"
        />
        <CommandList>
          <CommandEmpty>Type a query and press Enter to trace it.</CommandEmpty>
          {typed && (
            <CommandGroup heading="Trace">
              {/* value === the live input, so cmdk always ranks it top and
                  Enter submits the free-text query. */}
              <CommandItem value={typed} onSelect={() => select(typed)}>
                <Search className="text-indigo-500" />
                <span className="line-clamp-1 flex-1">
                  Trace “{typed}”
                </span>
                <CommandShortcut>
                  <CornerDownLeft className="h-3 w-3" />
                </CommandShortcut>
              </CommandItem>
            </CommandGroup>
          )}
          <CommandGroup heading="Recent">
            <CommandItem value={query} onSelect={() => select(query)}>
              <History className="text-zinc-400" />
              <span className="line-clamp-1 flex-1">{query}</span>
              <Badge variant="indigo" className="shrink-0">
                <GitBranch className="h-3 w-3" /> relational
              </Badge>
            </CommandItem>
          </CommandGroup>
          <CommandGroup heading="Preset queries">
            {QUERY_PRESETS.map((preset) => (
              <CommandItem
                key={preset.label}
                value={preset.label}
                onSelect={() => select(preset.label)}
              >
                <Sparkles className="text-indigo-500" />
                <span className="line-clamp-1 flex-1">{preset.label}</span>
                <Badge
                  variant={preset.intent === "relational" ? "indigo" : "zinc"}
                  className="shrink-0"
                >
                  {preset.intent}
                </Badge>
                <CommandShortcut>
                  <CornerDownLeft className="h-3 w-3" />
                </CommandShortcut>
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
      </CommandDialog>
    </>
  );
}
