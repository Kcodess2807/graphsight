import { Fragment, type ReactNode } from "react";
import { MEMORY_ENTITY_STYLES } from "./entityTheme";
import { cn } from "@/lib/utils";
import type { TraceNode } from "@/types/trace";

interface CitationPillProps {
  node: TraceNode;
  // pans the canvas camera to center this node
  onCite: (id: string) => void;
}

export function CitationPill({ node, onCite }: CitationPillProps) {
  const style = MEMORY_ENTITY_STYLES[node.type];
  const Icon = style.icon;
  return (
    <button
      type="button"
      onClick={() => onCite(node.id)}
      className={cn(
        "mx-0.5 inline-flex translate-y-[1px] items-center gap-1 rounded-full border px-2 py-[1px]",
        "border-[#131316] bg-white font-mono text-[11px] font-bold leading-5 shadow-[1px_2px_0_0_#131316]",
        "transition-transform duration-150 hover:-translate-y-0.5 hover:bg-emerald-50",
        style.text
      )}
      title={`Center ${node.label} on the canvas`}
    >
      <Icon className="h-3 w-3 opacity-80" />
      {node.label}
    </button>
  );
}

/**
 * Replaces every node-label mention inside an answer string with a clickable
 * CitationPill. Longest labels match first so "auth-service v2" wins over
 * "auth-service". Plain text segments pass through untouched.
 */
export function renderWithCitations(
  text: string,
  nodes: TraceNode[],
  onCite: (id: string) => void
): ReactNode {
  const byLabel = [...nodes]
    .filter((n) => n.label.length >= 3)
    .sort((a, b) => b.label.length - a.label.length);
  if (byLabel.length === 0) return text;

  const escaped = byLabel.map((n) =>
    n.label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
  );
  const pattern = new RegExp(`(${escaped.join("|")})`, "g");
  const parts = text.split(pattern);

  return parts.map((part, i) => {
    const node = byLabel.find((n) => n.label === part);
    if (!node) return <Fragment key={i}>{part}</Fragment>;
    return <CitationPill key={`${node.id}-${i}`} node={node} onCite={onCite} />;
  });
}
