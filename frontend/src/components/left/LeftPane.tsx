import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { HelpCircle, Lightbulb, Compass } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Wordmark } from "@/components/Wordmark";
import { AuthControls } from "@/components/auth/AuthControls";
import { SearchCommand } from "./SearchCommand";
import { GraphSwitcher } from "./GraphSwitcher";
import { AnswerCard } from "./AnswerCard";
import { LiveProgress } from "./LiveProgress";
import { SuggestionChips } from "./SuggestionChips";
import { RouterCard } from "./RouterCard";
import { ExecutionStepper } from "./ExecutionStepper";
import { MetricsFooter } from "./MetricsFooter";
import { fetchSuggestions, type Suggestion } from "@/lib/api";
import type { TraceState } from "@/types/trace";

// matches hedging phrases the LLM uses when context doesn't cover the question
const LOW_GROUNDING_RE =
  /\b(not contained|does not (mention|contain|include)|no (information|mention|details?)|cannot (find|answer)|isn'?t (mentioned|contained|available)|not (mentioned|present|available|found) in the)\b/i;

interface LeftPaneProps {
  trace: TraceState;
  loading: boolean;
  query: string;
  onQueryChange: (q: string) => void;
  onGraphSwitched?: () => void;
  answer?: string | null;
  answering?: boolean;
  onCiteNode?: (id: string) => void;
}

const fade = {
  hidden: { opacity: 0, y: 8 },
  show: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.08, duration: 0.4, ease: [0.16, 1, 0.3, 1] },
  }),
};

export function LeftPane({
  trace,
  loading,
  query,
  onQueryChange,
  onGraphSwitched,
  answer,
  answering,
  onCiteNode,
}: LeftPaneProps) {
  // suggestions for the active graph, refreshed on hot-swap
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const loadSuggestions = useCallback(() => {
    fetchSuggestions(5).then(setSuggestions).catch(() => setSuggestions([]));
  }, []);
  useEffect(() => {
    loadSuggestions();
  }, [loadSuggestions]);

  const handleGraphSwitched = useCallback(() => {
    loadSuggestions();
    onGraphSwitched?.();
  }, [loadSuggestions, onGraphSwitched]);

  const isEmpty = !loading && trace.graph.nodes.length === 0;
  // answer is present but reads like a non-answer
  const lowGrounded =
    !loading && !answering && !!answer && LOW_GROUNDING_RE.test(answer);

  return (
    <div className="flex h-full flex-col bg-zinc-50/60">
      {/* Header */}
      <div className="shrink-0 space-y-3 border-b border-border bg-white/70 px-5 pb-4 pt-5 backdrop-blur">
        <div className="flex items-center justify-between gap-2">
          <Wordmark />
          <div className="flex items-center gap-1.5">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  asChild
                  variant="outline"
                  size="sm"
                  className="h-8 gap-1.5 text-zinc-500"
                >
                  <Link
                    to="/docs/concepts"
                    aria-label="How it works — Concepts docs"
                  >
                    <HelpCircle className="h-4 w-4" />
                    <span className="hidden sm:inline">How it works</span>
                  </Link>
                </Button>
              </TooltipTrigger>
              <TooltipContent>Concepts · how Graphsight works</TooltipContent>
            </Tooltip>
            <AuthControls />
          </div>
        </div>
        <SearchCommand
          query={query}
          onQueryChange={onQueryChange}
          suggestions={suggestions}
        />
        <GraphSwitcher onSwitched={handleGraphSwitched} />
      </div>

      <ScrollArea className="flex-1">
        <div className="space-y-4 p-5">
          {loading ? (
            <LiveProgress />
          ) : isEmpty ? (
            <EmptyState
              suggestions={suggestions}
              onPick={onQueryChange}
            />
          ) : (
            <>
              <AnswerCard
                answer={answer ?? null}
                loading={Boolean(answering)}
                nodes={trace.graph.nodes}
                onCite={onCiteNode}
              />
              {lowGrounded && suggestions.length > 0 && (
                <LowGroundingHint
                  suggestions={suggestions}
                  onPick={onQueryChange}
                />
              )}
              <motion.div variants={fade} custom={0} initial="hidden" animate="show">
                <RouterCard weights={trace.weights} confidence={trace.confidence} />
              </motion.div>
              <motion.div variants={fade} custom={1} initial="hidden" animate="show">
                <ExecutionStepper steps={trace.steps} />
              </motion.div>
              <motion.div variants={fade} custom={2} initial="hidden" animate="show">
                <MetricsFooter metrics={trace.metrics} />
              </motion.div>
            </>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

function EmptyState({
  suggestions,
  onPick,
}: {
  suggestions: Suggestion[];
  onPick: (q: string) => void;
}) {
  return (
    <motion.div variants={fade} custom={0} initial="hidden" animate="show">
      <Card className="space-y-4 border-indigo-100 bg-indigo-50/30 p-5">
        <div className="flex items-center gap-2">
          <Compass className="h-4 w-4 text-indigo-500" />
          <h2 className="text-sm font-semibold tracking-tight text-zinc-800">
            Start exploring this graph
          </h2>
        </div>
        {suggestions.length > 0 ? (
          <>
            <p className="text-[13px] leading-relaxed text-zinc-600">
              Pick a question this graph can answer, or type your own above.
            </p>
            <SuggestionChips suggestions={suggestions} onPick={onPick} />
          </>
        ) : (
          <p className="text-[13px] leading-relaxed text-zinc-600">
            Type a question in the search box above to trace it through the
            graph.
          </p>
        )}
      </Card>
    </motion.div>
  );
}

function LowGroundingHint({
  suggestions,
  onPick,
}: {
  suggestions: Suggestion[];
  onPick: (q: string) => void;
}) {
  return (
    <Card className="space-y-3 border-amber-100 bg-amber-50/40 p-4">
      <div className="flex items-center gap-2">
        <Lightbulb className="h-4 w-4 text-amber-500" />
        <p className="text-[13px] font-medium text-zinc-700">
          This graph may not cover that. Try one of these:
        </p>
      </div>
      <SuggestionChips suggestions={suggestions} onPick={onPick} />
    </Card>
  );
}

function LeftPaneSkeleton() {
  return (
    <div className="space-y-4">
      <Card className="space-y-4 p-5">
        <div className="flex items-center justify-between">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-5 w-20 rounded-full" />
        </div>
        <Skeleton className="h-2 w-full rounded-full" />
        <Skeleton className="h-2 w-full rounded-full" />
        <Skeleton className="h-px w-full" />
        <Skeleton className="h-2 w-full rounded-full" />
      </Card>
      <Card className="space-y-5 p-5">
        <Skeleton className="h-5 w-28" />
        {[0, 1, 2].map((i) => (
          <div key={i} className="flex gap-3.5">
            <Skeleton className="h-8 w-8 rounded-full" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-3 w-full" />
            </div>
          </div>
        ))}
      </Card>
      <div className="grid grid-cols-2 gap-3">
        <Skeleton className="col-span-2 h-24 rounded-xl" />
        <Skeleton className="h-20 rounded-xl" />
        <Skeleton className="h-20 rounded-xl" />
      </div>
    </div>
  );
}
