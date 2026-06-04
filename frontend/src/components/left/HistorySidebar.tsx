import { History, MessageSquare, Plus } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ChatSessionDto } from "@/lib/api";

interface HistorySidebarProps {
  sessions: ChatSessionDto[];
  activeSessionId: string | null;
  loading?: boolean;
  onSelect: (sessionId: string) => void;
  onNewChat: () => void;
  className?: string;
}

/** Short, locale-aware timestamp for a session row.
 *
 * `created_at` is stored as UTC, but the backend serializes it without a
 * timezone marker (e.g. "2026-06-04T20:59:00"). The browser would otherwise
 * parse that as LOCAL time — so we append "Z" to force UTC interpretation,
 * then let toLocaleString render it in the user's actual local timezone. */
function formatWhen(iso: string): string {
  if (!iso) return "";
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(iso);
  const d = new Date(hasTz ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Left rail listing a signed-in user's past chat sessions. Clicking a row
 * re-hydrates the canvas from stored traces (no LLM); "New chat" clears the
 * active session and empties the canvas.
 */
export function HistorySidebar({
  sessions,
  activeSessionId,
  loading,
  onSelect,
  onNewChat,
  className,
}: HistorySidebarProps) {
  return (
    <aside
      className={cn(
        "flex h-full w-64 flex-col border-r border-border bg-zinc-50/60",
        className
      )}
    >
      <div className="flex items-center gap-2 px-4 py-3.5">
        <History className="h-4 w-4 text-zinc-500" />
        <span className="text-sm font-semibold tracking-tight text-zinc-700">
          History
        </span>
      </div>

      <div className="px-3 pb-2">
        <Button
          onClick={onNewChat}
          size="sm"
          variant="outline"
          className="w-full justify-start gap-2 border-zinc-200 bg-white text-zinc-700"
        >
          <Plus className="h-4 w-4" />
          New chat
        </Button>
      </div>

      <ScrollArea className="min-h-0 flex-1 px-2">
        {sessions.length === 0 ? (
          <p className="px-2 py-6 text-center text-xs text-zinc-400">
            {loading ? "Loading sessions…" : "No saved sessions yet."}
          </p>
        ) : (
          <ul className="space-y-0.5 pb-4">
            {sessions.map((s) => {
              const active = s.id === activeSessionId;
              return (
                <li key={s.id}>
                  <button
                    type="button"
                    onClick={() => onSelect(s.id)}
                    title={s.title}
                    className={cn(
                      "flex w-full items-start gap-2 rounded-lg px-2.5 py-2 text-left transition-colors",
                      active
                        ? "bg-indigo-50 text-indigo-700"
                        : "text-zinc-600 hover:bg-zinc-100"
                    )}
                  >
                    <MessageSquare
                      className={cn(
                        "mt-0.5 h-4 w-4 shrink-0",
                        active ? "text-indigo-500" : "text-zinc-400"
                      )}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">
                        {s.title || "Untitled chat"}
                      </span>
                      <span className="block text-[11px] text-zinc-400">
                        {formatWhen(s.created_at)}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </ScrollArea>
    </aside>
  );
}
