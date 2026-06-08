import {
  Fragment,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Sparkles, Copy, Check } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { TraceNode } from "@/types/trace";

// escape regex metachars so labels like "PR #5818" match literally
function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// turn entity mentions in the answer into clickable citation chips
function renderWithCitations(
  answer: string,
  nodes: TraceNode[],
  onCite: (id: string) => void
): ReactNode {
  // label(lowercased) -> node id, first occurrence wins
  const labelToId = new Map<string, string>();
  for (const n of nodes) {
    const key = n.label?.trim().toLowerCase();
    if (key && !labelToId.has(key)) labelToId.set(key, n.id);
  }
  const labels = [...labelToId.keys()]
    // skip 1-2 char labels, too noisy; longest-first so longer labels win
    .filter((l) => l.length >= 3)
    .sort((a, b) => b.length - a.length);

  if (labels.length === 0) return answer;

  // Lookaround guards instead of \b: the match must not be flanked by a word
  // char, so "click" won't fire inside "clicked". We use (?<!\w)…(?!\w) rather
  // than \b because labels can have NON-word edges — e.g. "PR #5818" or "#5818"
  // — where \b asserts a word/non-word transition that doesn't exist at the
  // symbol and would fail to match. "Not preceded/followed by a word char"
  // works for both word-edged and symbol-edged labels.
  const re = new RegExp(
    `(?<!\\w)(?:${labels.map(escapeRegExp).join("|")})(?!\\w)`,
    "gi"
  );
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
    if (m.index === re.lastIndex) re.lastIndex++; // guard zero-width loops
  }
  if (last < answer.length) out.push(<Fragment key={key++}>{answer.slice(last)}</Fragment>);
  return out;
}

export function AnswerCard({
  answer,
  loading,
  nodes,
  onCite,
}: {
  answer: string | null;
  loading: boolean;
  nodes?: TraceNode[];
  onCite?: (id: string) => void;
}) {
  // All hooks run unconditionally, BEFORE the early return below — otherwise the
  // hook count would change between a null render and a real one (rules-of-hooks
  // violation). copied = the brief post-click confirmation state.
  const [copied, setCopied] = useState(false);
  const copyTimer = useRef<number | null>(null);

  // clear the pending "Copied!" timeout if we unmount mid-countdown
  useEffect(
    () => () => {
      if (copyTimer.current) window.clearTimeout(copyTimer.current);
    },
    []
  );

  const handleCopy = useCallback(async () => {
    if (!answer) return;
    try {
      await navigator.clipboard.writeText(answer);
      setCopied(true);
      // reset to idle after 2s; restart the timer if clicked again meanwhile
      if (copyTimer.current) window.clearTimeout(copyTimer.current);
      copyTimer.current = window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard API is unavailable in insecure contexts — fail silently
    }
  }, [answer]);

  const body = useMemo(() => {
    if (!answer) return null;
    if (!nodes || !onCite) return answer;
    return renderWithCitations(answer, nodes, onCite);
  }, [answer, nodes, onCite]);

  if (!loading && !answer) return null;

  const hasText = !!answer;
  // streaming once tokens start arriving; skeleton only covers the gap before that
  const streaming = loading && hasText;

  return (
    <Card className="space-y-2.5 border-indigo-100 bg-indigo-50/40 p-5">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-indigo-500" />
          <h2 className="text-sm font-semibold tracking-tight text-zinc-800">
            Answer
          </h2>
        </div>
        {/* Copy button: shown once there's text, disabled until streaming ends */}
        {hasText && (
          <button
            type="button"
            onClick={handleCopy}
            disabled={streaming}
            title={streaming ? "Wait for the answer to finish" : "Copy answer"}
            className="flex items-center gap-1 rounded-md px-1.5 py-1 text-[11px] font-medium text-zinc-500 transition-colors hover:bg-indigo-100/70 hover:text-indigo-700 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent disabled:hover:text-zinc-500"
          >
            {copied ? (
              <>
                <Check className="h-3.5 w-3.5" />
                Copied!
              </>
            ) : (
              <>
                <Copy className="h-3.5 w-3.5" />
                Copy
              </>
            )}
          </button>
        )}
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
