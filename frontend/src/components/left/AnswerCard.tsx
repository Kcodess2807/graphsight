import { Sparkles } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * The plain-language answer (the "G" in GraphRAG) — synthesized from the
 * retrieved context so a non-technical reader gets the takeaway without
 * decoding the graph. The graph below is the evidence behind it.
 */
export function AnswerCard({
  answer,
  loading,
}: {
  answer: string | null;
  loading: boolean;
}) {
  if (!loading && !answer) return null;

  return (
    <Card className="space-y-2.5 border-indigo-100 bg-indigo-50/40 p-5">
      <div className="flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-indigo-500" />
        <h2 className="text-sm font-semibold tracking-tight text-zinc-800">
          Answer
        </h2>
      </div>
      {loading ? (
        <div className="space-y-2">
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-11/12" />
          <Skeleton className="h-3 w-4/5" />
        </div>
      ) : (
        <p className="text-[13px] leading-relaxed text-zinc-700">{answer}</p>
      )}
      <p className="text-[11px] text-zinc-400">
        Generated from the retrieved context — the graph below is the evidence.
      </p>
    </Card>
  );
}
