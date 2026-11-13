import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { CommandPanel, type SuggestedTrace } from "./CommandPanel";
import { GraphCanvas, type FocusRequest } from "./GraphCanvas";
import { InspectorPanel } from "./InspectorPanel";
import { cn, MOD_KEY } from "@/lib/utils";
import type { ChatSessionDto } from "@/lib/api";
import type { TraceNode, TraceState } from "@/types/trace";

const SIDEBAR_W = 300;
// Tailwind's md: below this the sidebar overlays the canvas
const NARROW = 768;

interface AppLayoutProps {
  trace: TraceState;
  tracing: boolean;
  answer: string | null;
  // an error or status the user should act on
  notice?: string | null;
  suggestions: SuggestedTrace[];
  recentQueries: string[];
  // omitted for imported traces, which have no backend to query
  onQuery?: (q: string) => void;
  // optional session history (signed-in users)
  sessions?: ChatSessionDto[];
  activeSessionId?: string | null;
  onSelectSession?: (id: string) => void;
  onNewChat?: () => void;
  newChatLabel?: string;
}

/**
 * The memory-tool shell: command sidebar (collapsible with the \\ shortcut),
 * full-bleed canvas, floating inspector. Mod+K focuses the trace input; Esc
 * closes the inspector.
 */
export function AppLayout({
  trace,
  tracing,
  answer,
  notice,
  suggestions,
  recentQueries,
  onQuery,
  sessions,
  activeSessionId,
  onSelectSession,
  onNewChat,
  newChatLabel,
}: AppLayoutProps) {
  const [collapsed, setCollapsed] = useState(() => window.innerWidth < NARROW);
  const [selected, setSelected] = useState<TraceNode | null>(null);
  const [focus, setFocus] = useState<FocusRequest | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  // leaves room for the toggle beside the open sidebar on phones
  const sidebarW = Math.min(SIDEBAR_W, window.innerWidth - 56);

  // nonce lets the same citation re-trigger the camera pan
  const focusNodeById = useCallback((id: string) => {
    setFocus((prev) => ({ id, nonce: (prev?.nonce ?? 0) + 1 }));
  }, []);

  const selectNode = useCallback((node: TraceNode | null) => {
    if (node) returnFocus.current = document.activeElement as HTMLElement;
    setSelected(node);
  }, []);

  const closeInspector = useCallback(() => {
    setSelected(null);
    returnFocus.current?.focus();
    returnFocus.current = null;
  }, []);

  // citation click = pan camera AND open the inspector for that node
  const citeNode = useCallback(
    (id: string) => {
      focusNodeById(id);
      const node = trace.graph.nodes.find((n) => n.id === id);
      if (node) selectNode(node);
    },
    [focusNodeById, selectNode, trace.graph.nodes]
  );

  // global keys: Mod+K to search, Mod+\\ for the sidebar, Esc for the inspector
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === "k") {
        e.preventDefault();
        // the input can't take focus until the sidebar is visible again
        flushSync(() => setCollapsed(false));
        inputRef.current?.focus();
      } else if (mod && e.key === "\\") {
        e.preventDefault();
        setCollapsed((v) => !v);
      } else if (e.key === "Escape") {
        closeInspector();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [closeInspector]);

  // a fresh trace invalidates the open inspector's node data
  useEffect(() => setSelected(null), [trace.id]);

  return (
    <div className="m-light relative flex h-[100dvh] overflow-hidden bg-paper font-sans text-ink antialiased">
      {/* ── command sidebar ────────────────────────────────────── */}
      <div
        style={{ width: collapsed ? 0 : sidebarW }}
        className="relative z-20 h-full shrink-0 overflow-hidden border-r border-[#131316] max-md:absolute max-md:inset-y-0 max-md:left-0"
      >
        {/* invisible, not just clipped: a collapsed sidebar must leave the tab order */}
        <div style={{ width: sidebarW }} className={cn("h-full", collapsed && "invisible")}>
          <CommandPanel
            trace={trace}
            tracing={tracing}
            answer={answer}
            notice={notice}
            suggestions={suggestions}
            recentQueries={recentQueries}
            onQuery={onQuery}
            onCite={citeNode}
            inputRef={inputRef}
            sessions={sessions}
            activeSessionId={activeSessionId}
            onSelectSession={onSelectSession}
            onNewChat={onNewChat}
            newChatLabel={newChatLabel}
          />
        </div>
      </div>

      {/* ── canvas + floating chrome ───────────────────────────── */}
      <main tabIndex={-1} className="relative min-w-0 flex-1 outline-none">
        <GraphCanvas
          trace={trace}
          tracing={tracing}
          focusNode={focus}
          onSelectNode={selectNode}
          readOnly={!onQuery}
        />

        {/* sidebar toggle floats on the canvas so it works while collapsed */}
        <button
          type="button"
          onClick={() => setCollapsed((v) => !v)}
          aria-label={`${collapsed ? "Open" : "Collapse"} sidebar (${MOD_KEY}\\)`}
          className={cn(
            "absolute left-4 top-4 z-20 flex h-9 w-9 items-center justify-center rounded-lg",
            "max-md:fixed max-md:left-auto max-md:right-2",
            "border border-[#131316] bg-white text-ink shadow-[2px_3px_0_0_#131316]",
            "transition-transform duration-150 hover:-translate-y-0.5"
          )}
        >
          {collapsed ? (
            <PanelLeftOpen className="h-4 w-4" />
          ) : (
            <PanelLeftClose className="h-4 w-4" />
          )}
        </button>

        <InspectorPanel node={selected} onClose={closeInspector} onCenter={focusNodeById} />
      </main>
    </div>
  );
}
