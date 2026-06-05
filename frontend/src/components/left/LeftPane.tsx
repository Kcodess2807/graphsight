import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { HelpCircle } from "lucide-react";
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
import { RouterCard } from "./RouterCard";
import { ExecutionStepper } from "./ExecutionStepper";
import { MetricsFooter } from "./MetricsFooter";
import type { TraceState } from "@/types/trace";

interface LeftPaneProps {
  trace: TraceState;
  loading: boolean;
  query: string;
  onQueryChange: (q: string) => void;
  /** Called after the active graph is hot-swapped (parent resets the canvas). */
  onGraphSwitched?: () => void;
  /** Plain-language answer + its loading state (the "G" in GraphRAG). */
  answer?: string | null;
  answering?: boolean;
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
}: LeftPaneProps) {
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
              <TooltipContent>Concepts · how TraceRAG works</TooltipContent>
            </Tooltip>
            <AuthControls />
          </div>
        </div>
        <SearchCommand query={query} onQueryChange={onQueryChange} />
        <GraphSwitcher onSwitched={onGraphSwitched} />
      </div>

      <ScrollArea className="flex-1">
        <div className="space-y-4 p-5">
          {loading ? (
            <LeftPaneSkeleton />
          ) : (
            <>
              <AnswerCard answer={answer ?? null} loading={Boolean(answering)} />
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
