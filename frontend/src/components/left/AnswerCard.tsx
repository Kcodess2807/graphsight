import { Fragment, type ReactNode, useMemo } from "react";
import { Sparkles } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { TraceNode } from "@/types/trace";

/** Escape a label so it can be embedded literally in a RegExp (labels contain
 *  `#`, `.`, `-`, etc. — e.g. "PR #5818"). */
function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Turn an answer string into React nodes where any mention of a graph entity
 * becomes a clickable citation chip. This is the "evidence" link the UI
 * promises — clicking a name pans/highlights that node on the canvas, so the
 * reader can verify the claim against the actual traced sub-graph.
 *
 * Matching notes:
 *   - We build ONE alternation regex from every node label, longest-first.
 *     JS alternation is leftmost-first, so ordering longer labels first makes
 *     each position resolve to the LONGEST match (e.g. "PR #5818" wins over a
 *     bare "5818") instead of a partial.
 *   - Case-insensitive match, but the original casing from the answer is shown.
 */
function renderWithCitations(
  answer: string,
  nodes: TraceNode[],
  onCite: (id: string) => void
): ReactNode {
  // label(lowercased) -> node id. First occurrence wins on duplicate labels.
  const labelToId = new Map<string, string>();
  for (const n of nodes) {
    const key = n.label?.trim().toLowerCase();
    if (key && !labelToId.has(key)) labelToId.set(key, n.id);
  }
  const labels = [...labelToId.keys()]
    // Skip 1-2 char labels — too noisy, they'd match common words/initials.
    .filter((l) => l.length >= 3)
    .sort((a, b) => b.length - a.length);

  if (labels.length === 0) return answer;

  const re = new RegExp(labels.map(escapeRegExp).join("|"), "gi");
  const out: ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  let key = 0;
  while ((m = re.exec(answer)) !== null) {
    if (m.index > last) out.push(<Fragment key={key++}>{answer.slice(last, m.index)}</Fragment>);
    const matched = m[0];
    const id = labelToId.get(matched.toLowerCase());
    if (id) {
      out.push(
        <button
          key={key++}
          type="button"
          onClick={() => onCite(id)}
          title="Show this entity on the graph"
          className="rounded bg-indigo-100/70 px-1 font-medium text-indigo-700 underline decoration-indigo-300 decoration-dotted underline-offset-2 transition-colors hover:bg-indigo-200/70 hover:decoration-indigo-500"
        >
          {matched}
        </button>
      );
    } else {
      out.push(<Fragment key={key++}>{matched}</Fragment>);
    }
    last = m.index + matched.length;
    if (m.index === re.lastIndex) re.lastIndex++; // guard against zero-width loops
  }
  if (last < answer.length) out.push(<Fragment key={key++}>{answer.slice(last)}</Fragment>);
  return out;
}

/**
 * The plain-language answer (the "G" in GraphRAG) — synthesized from the
 * retrieved context so a non-technical reader gets the takeaway without
 * decoding the graph. The graph below is the evidence behind it; entity
 * mentions are clickable citations into that graph (see renderWithCitations).
 */
export function AnswerCard({
  answer,
  loading,
  nodes,
  onCite,
}: {
  answer: string | null;
  loading: boolean;
  /** Graph nodes for citation matching (omit to render plain text). */
  nodes?: TraceNode[];
  /** Focus a node on the canvas when its citation is clicked. */
  onCite?: (id: string) => void;
}) {
  if (!loading && !answer) return null;

  const hasText = !!answer;
  // Streaming = we're loading AND tokens have already started arriving. In that
  // window we show the growing text with a cursor, NOT the skeleton (the
  // skeleton is only for the brief gap before the first token lands).
  const streaming = loading && hasText;

  // Memoised so we don't re-scan the answer on every parent re-render. While
  // streaming this re-runs per token, but the answer is short so it's cheap.
  const body = useMemo(() => {
    if (!answer) return null;
    if (!nodes || !onCite) return answer;
    return renderWithCitations(answer, nodes, onCite);
  }, [answer, nodes, onCite]);

  return (
    <Card className="space-y-2.5 border-indigo-100 bg-indigo-50/40 p-5">
      <div className="flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-indigo-500" />
        <h2 className="text-sm font-semibold tracking-tight text-zinc-800">
          Answer
        </h2>
      </div>
      {loading && !hasText ? (
        <div className="space-y-2">
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-11/12" />
          <Skeleton className="h-3 w-4/5" />
        </div>
      ) : (
        <p className={cn("text-[13px] leading-relaxed text-zinc-700")}>
          {body}
          {/* Blinking caret while tokens are still streaming in. */}
          {streaming && (
            <span className="ml-0.5 inline-block h-3.5 w-[2px] -translate-y-px animate-pulse bg-indigo-400 align-middle" />
          )}
        </p>
      )}
      <p className="text-[11px] text-zinc-400">
        Generated from the retrieved context — the graph below is the evidence.
        {onCite ? " Click a highlighted name to find it." : ""}
      </p>
    </Card>
  );
}
