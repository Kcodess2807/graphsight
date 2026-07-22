import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { CommandPanel, type SuggestedTrace } from "./CommandPanel";
import { GraphCanvas, type FocusRequest } from "./GraphCanvas";
import { InspectorPanel } from "./InspectorPanel";
import { cn } from "@/lib/utils";
import type { ChatSessionDto } from "@/lib/api";
import type { TraceNode, TraceState } from "@/types/trace";

const SIDEBAR_W = 300;

interface AppLayoutProps {
  trace: TraceState;
  tracing: boolean;
  answer: string | null;
  suggestions: SuggestedTrace[];
  recentQueries: string[];
  onQuery: (q: string) => void;
  // optional session history (signed-in users)
  sessions?: ChatSessionDto[];
  activeSessionId?: string | null;
  onSelectSession?: (id: string) => void;
  onNewChat?: () => void;
}

/**
 * The memory-tool shell, light neubrutalist edition: command sidebar
 * (left, 300px, collapsible with ⌘\), infinite canvas (full bleed),
 * floating hard-shadow inspector. ⌘K focuses the trace input; Esc closes
 * the inspector.
 */
export function AppLayout({
  trace,
  tracing,
  answer,
  suggestions,
  recentQueries,
  onQuery,
  sessions,
  activeSessionId,
  onSelectSession,
  onNewChat,
}: AppLayoutProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [selected, setSelected] = useState<TraceNode | null>(null);
  const [focus, setFocus] = useState<FocusRequest | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // nonce lets the same citation re-trigger the camera pan
  const focusNodeById = useCallback((id: string) => {
    setFocus((prev) => ({ id, nonce: (prev?.nonce ?? 0) + 1 }));
  }, []);

  // citation click = pan camera AND open the inspector for that node
  const citeNode = useCallback(
    (id: string) => {
      focusNodeById(id);
      const node = trace.graph.nodes.find((n) => n.id === id);
      if (node) setSelected(node);
    },
    [focusNodeById, trace.graph.nodes]
  );

  // global keys: ⌘K → search, ⌘\ → sidebar, Esc → inspector
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCollapsed(false);
        // wait a frame so the input exists if the sidebar was collapsed
        requestAnimationFrame(() => inputRef.current?.focus());
      } else if (mod && e.key === "\\") {
        e.preventDefault();
        setCollapsed((v) => !v);
      } else if (e.key === "Escape") {
        setSelected(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // a fresh trace invalidates the open inspector's node data
  useEffect(() => setSelected(null), [trace.id]);

  return (
    <div className="m-light relative flex h-[100dvh] overflow-hidden bg-paper font-sans text-ink antialiased">
      {/* ── command sidebar ────────────────────────────────────── */}
      <motion.div
        initial={false}
        animate={{ width: collapsed ? 0 : SIDEBAR_W }}
        transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
        className="relative z-20 h-full shrink-0 overflow-hidden border-r border-[#131316]"
      >
        <div style={{ width: SIDEBAR_W }} className="h-full">
          <CommandPanel
            trace={trace}
            tracing={tracing}
            answer={answer}
            suggestions={suggestions}
            recentQueries={recentQueries}
            onQuery={onQuery}
            onCite={citeNode}
            inputRef={inputRef}
            sessions={sessions}
            activeSessionId={activeSessionId}
            onSelectSession={onSelectSession}
            onNewChat={onNewChat}
          />
        </div>
      </motion.div>

      {/* ── canvas + floating chrome ───────────────────────────── */}
      <div className="relative min-w-0 flex-1">
        <GraphCanvas
          trace={trace}
          tracing={tracing}
          focusNode={focus}
          onSelectNode={setSelected}
        />

        {/* sidebar toggle floats on the canvas so it works while collapsed */}
        <button
          type="button"
          onClick={() => setCollapsed((v) => !v)}
          aria-label={collapsed ? "Open sidebar (⌘\\)" : "Collapse sidebar (⌘\\)"}
          className={cn(
            "absolute left-4 top-4 z-20 flex h-9 w-9 items-center justify-center rounded-lg",
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

        <InspectorPanel
          node={selected}
          onClose={() => setSelected(null)}
          onCenter={focusNodeById}
        />
      </div>
    </div>
  );
}
