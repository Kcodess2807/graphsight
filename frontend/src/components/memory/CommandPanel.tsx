import { useState, type RefObject } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ChevronRight,
  CornerDownLeft,
  History,
  MessageSquare,
  Plus,
  Route,
  Search,
  Sparkles,
} from "lucide-react";
import { renderWithCitations } from "./CitationPill";
import { cn } from "@/lib/utils";
import type { ChatSessionDto } from "@/lib/api";
import type { TraceState } from "@/types/trace";

const LIME = "#C8F169";

export interface SuggestedTrace {
  label: string;
  // full query submitted when the suggestion is clicked
  query: string;
}

interface CommandPanelProps {
  trace: TraceState;
  tracing: boolean;
  // streamed plain-language recall; entity mentions become citation pills
  answer: string | null;
  suggestions: SuggestedTrace[];
  recentQueries: string[];
  onQuery: (q: string) => void;
  onCite: (id: string) => void;
  // owned by AppLayout so ⌘K can focus it from anywhere
  inputRef: RefObject<HTMLInputElement>;
  // session history — only rendered when the host app provides it (signed-in)
  sessions?: ChatSessionDto[];
  activeSessionId?: string | null;
  onSelectSession?: (id: string) => void;
  onNewChat?: () => void;
}

export function CommandPanel({
  trace,
  tracing,
  answer,
  suggestions,
  recentQueries,
  onQuery,
  onCite,
  inputRef,
  sessions,
  activeSessionId,
  onSelectSession,
  onNewChat,
}: CommandPanelProps) {
  const [draft, setDraft] = useState("");

  const submit = () => {
    const q = draft.trim();
    if (q && !tracing) onQuery(q);
  };

  return (
    <div className="flex h-full w-full flex-col bg-white">
      {/* ── header: wordmark + live dot + new chat ─────────────── */}
      <div className="flex items-center gap-2.5 px-4 pb-4 pt-4">
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-500 opacity-50 [animation-duration:2s]" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
        </span>
        <span className="font-display text-[15px] font-bold tracking-tight text-[#131316]">
          Graphsight
        </span>
        <span
          className="rounded-full border border-[#131316] px-2 py-0.5 font-mono text-[9px] font-bold uppercase tracking-[0.2em] text-[#131316]"
          style={{ backgroundColor: LIME }}
        >
          memory
        </span>
        {onNewChat && (
          <button
            type="button"
            onClick={onNewChat}
            title="New chat"
            className="ml-auto flex h-7 w-7 items-center justify-center rounded-lg border border-[#131316] bg-white text-[#131316] shadow-[2px_2px_0_0_#131316] transition-transform duration-150 hover:-translate-y-0.5"
          >
            <Plus className="h-3.5 w-3.5" strokeWidth={2.5} />
          </button>
        )}
      </div>

      {/* ── command input ──────────────────────────────────────── */}
      <div className="px-3">
        <div
          className={cn(
            "group flex items-center gap-2.5 rounded-xl border border-[#131316] bg-white px-3.5 py-3",
            "transition-shadow duration-150 focus-within:shadow-[3px_4px_0_0_#059669]"
          )}
        >
          <Search className="h-4 w-4 shrink-0 text-zinc-400 group-focus-within:text-emerald-600" />
          <input
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            placeholder="Trace anything…"
            spellCheck={false}
            className={cn(
              "min-w-0 flex-1 bg-transparent text-[13px] text-[#131316]",
              "placeholder:text-zinc-400 focus:outline-none"
            )}
          />
          {draft ? (
            <button
              type="button"
              onClick={submit}
              aria-label="Run trace"
              className="rounded-md border border-[#131316] bg-white p-1 text-[#131316] shadow-[1px_2px_0_0_#131316] transition-transform duration-150 hover:-translate-y-0.5"
            >
              <CornerDownLeft className="h-3 w-3" strokeWidth={2.5} />
            </button>
          ) : (
            <kbd className="rounded-md border border-zinc-300 bg-zinc-50 px-1.5 py-0.5 font-mono text-[10px] font-bold text-zinc-500">
              ⌘K
            </kbd>
          )}
        </div>
        {/* progress hairline under the input while a query runs */}
        <div className="mt-2.5 h-[3px] overflow-hidden rounded-full bg-zinc-100">
          {tracing && (
            <div className="h-full w-1/3 animate-scan bg-gradient-to-r from-transparent via-emerald-500 to-transparent" />
          )}
        </div>
      </div>

      {/* ── scrollable body ────────────────────────────────────── */}
      <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto px-3 pb-3">
        {/* recall — the answer, rendered as prose with citation pills */}
        <AnimatePresence>
          {answer !== null && (
            <motion.section
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.35, ease: "easeOut" }}
              className="mt-4 rounded-xl border border-[#131316] bg-white p-4 shadow-[3px_4px_0_0_#131316]"
            >
              <SectionLabel icon={Sparkles}>Recall</SectionLabel>
              <p className="mt-2.5 text-[13px] leading-relaxed text-zinc-700">
                {renderWithCitations(answer, trace.graph.nodes, onCite)}
                {tracing && (
                  <span className="ml-0.5 inline-block h-3.5 w-[7px] animate-pulse bg-emerald-500 align-middle" />
                )}
              </p>
            </motion.section>
          )}
        </AnimatePresence>

        {/* session history — present only for signed-in users */}
        {sessions && onSelectSession && (
          <Accordion title="Sessions" icon={MessageSquare} defaultOpen={sessions.length > 0}>
            {sessions.length === 0 ? (
              <p className="px-2 py-1.5 text-xs text-zinc-400">No saved sessions.</p>
            ) : (
              sessions.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => onSelectSession(s.id)}
                  className={cn(
                    "block w-full truncate rounded-lg px-2 py-1.5 text-left text-xs transition-colors",
                    s.id === activeSessionId
                      ? "bg-[#131316] font-semibold text-white"
                      : "text-zinc-600 hover:bg-zinc-100 hover:text-[#131316]"
                  )}
                >
                  {s.title || "Untitled"}
                </button>
              ))
            )}
          </Accordion>
        )}

        {/* suggested traces */}
        <Accordion title="Suggested Traces" icon={Route} defaultOpen>
          {suggestions.map((s) => (
            <RowButton key={s.query} onClick={() => onQuery(s.query)}>
              {s.label}
            </RowButton>
          ))}
        </Accordion>

        {/* recent queries */}
        <Accordion title="Recent Queries" icon={History} defaultOpen={recentQueries.length > 0}>
          {recentQueries.length === 0 ? (
            <p className="px-2 py-1.5 text-xs text-zinc-400">Nothing traced yet.</p>
          ) : (
            recentQueries.map((q, i) => (
              <RowButton key={`${q}-${i}`} onClick={() => onQuery(q)} mono>
                {q}
              </RowButton>
            ))
          )}
        </Accordion>
      </div>

      {/* ── metrics footer — the speed is the brand, keep it visible ── */}
      <div className="flex items-center justify-between border-t border-[#131316] px-4 py-3">
        <span className="font-mono text-[10px] font-bold uppercase tracking-widest text-zinc-400">
          {trace.graph.nodes.length} nodes ·{" "}
          {trace.graph.edges.filter((e) => e.active).length} traced
        </span>
        <span className="font-mono text-[11px] font-bold text-emerald-600">
          {trace.metrics.queryTimeSec > 0
            ? `${Math.round(trace.metrics.queryTimeSec * 1000)}ms`
            : "—"}
        </span>
      </div>
    </div>
  );
}

function SectionLabel({
  icon: Icon,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
}) {
  return (
    <span className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-emerald-600">
      <Icon className="h-3 w-3" />
      {children}
    </span>
  );
}

function Accordion({
  title,
  icon: Icon,
  defaultOpen = false,
  children,
}: {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="mt-4">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-1.5 rounded-lg px-2 py-1.5 text-left hover:bg-zinc-100"
      >
        <ChevronRight
          className={cn(
            "h-3 w-3 text-zinc-400 transition-transform duration-200",
            open && "rotate-90"
          )}
        />
        <Icon className="h-3.5 w-3.5 text-zinc-500" />
        <span className="text-xs font-bold text-[#131316]">{title}</span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="overflow-hidden"
          >
            <div className="mt-1 space-y-0.5 pl-4">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}

function RowButton({
  onClick,
  mono,
  children,
}: {
  onClick: () => void;
  mono?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "block w-full truncate rounded-lg px-2 py-1.5 text-left text-xs text-zinc-600",
        "transition-colors hover:bg-emerald-50 hover:text-emerald-700",
        mono && "font-mono text-[11px]"
      )}
    >
      {children}
    </button>
  );
}
