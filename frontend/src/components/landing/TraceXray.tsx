import { useState } from "react";
import {
  GitCommitHorizontal,
  GitPullRequest,
  Server,
  Ticket,
  TriangleAlert,
  User,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { CARD, EMERALD, LIME, Reveal, SectionHead } from "./_shared";

/* the trace from example/failure_demo.py — an agent that answers wrong,
   and the retrieval evidence that shows why */

type Kind = "PR" | "Ticket" | "Service" | "Person";

interface XrayNode {
  id: string;
  label: string;
  kind: Kind;
  score: number;
  used: boolean;
  x: number;
  y: number;
  snippet: string;
  verdict?: "trap" | "cause";
}

const NODES: XrayNode[] = [
  {
    id: "pr_4102",
    label: "PR #4102",
    kind: "PR",
    score: 0.91,
    used: true,
    x: 82,
    y: 78,
    snippet:
      "fix: checkout payment failures under load — add retry with timeout. Merged 8 months ago by Marco T.",
    verdict: "trap",
  },
  {
    id: "tkt_2291",
    label: "INC-2291",
    kind: "Ticket",
    score: 0.78,
    used: false,
    x: 13,
    y: 50,
    snippet:
      "sev1, open: checkout payment auth declining ~100% since the 2026-07-24 deploy. Rollback restores service.",
  },
  {
    id: "svc_payment",
    label: "payment-service",
    kind: "Service",
    score: 0.55,
    used: false,
    x: 46,
    y: 50,
    snippet:
      "authorizes and captures card payments for checkout. Depends on stripe-sdk. Owned by the payments team.",
  },
  {
    id: "pr_4977",
    label: "PR #4977",
    kind: "PR",
    score: 0.34,
    used: false,
    x: 82,
    y: 20,
    snippet:
      "chore: bump stripe-sdk 11.2 → 12.0. Merged 2026-07-24. Release notes: v12 removes the legacy auth_flow flag.",
    verdict: "cause",
  },
  {
    id: "person_lena",
    label: "Lena K.",
    kind: "Person",
    score: 0.2,
    used: false,
    x: 46,
    y: 12,
    snippet: "platform engineer. Handles dependency upgrades.",
  },
];

const EDGES = [
  { from: "tkt_2291", to: "svc_payment", rel: "REPORTS_ON", traced: true },
  { from: "pr_4977", to: "svc_payment", rel: "TOUCHES", traced: true },
  { from: "person_lena", to: "pr_4977", rel: "AUTHORED", traced: true },
  { from: "pr_4102", to: "svc_payment", rel: "TOUCHES", traced: false },
];

const ICONS: Record<Kind, typeof GitPullRequest> = {
  PR: GitPullRequest,
  Ticket: Ticket,
  Service: Server,
  Person: User,
};

const TINT: Record<Kind, string> = {
  PR: "bg-indigo-500/10 text-indigo-600 border-indigo-500/20",
  Ticket: "bg-sky-500/10 text-sky-600 border-sky-500/20",
  Service: "bg-slate-500/10 text-slate-600 border-slate-500/20",
  Person: "bg-amber-500/10 text-amber-600 border-amber-500/20",
};

const byId = (id: string) => NODES.find((n) => n.id === id)!;

function ScoreChip({ score, muted }: { score: number; muted?: boolean }) {
  return (
    <span
      className={cn(
        "shrink-0 rounded-full border px-1.5 py-px font-mono text-[10px] font-bold",
        muted ? "border-zinc-300 text-zinc-400" : "border-[#131316] text-[#131316]"
      )}
      style={muted ? undefined : { backgroundColor: LIME }}
    >
      {score.toFixed(2)}
    </span>
  );
}

/* mode A — what plain similarity ranking hands the model */
function RankedView({ onPick }: { onPick: (n: XrayNode) => void }) {
  const ranked = [...NODES].sort((a, b) => b.score - a.score);
  return (
    <div className="flex flex-col gap-2.5">
      {ranked.map((n, i) => {
        const Icon = ICONS[n.kind];
        return (
          <button
            key={n.id}
            type="button"
            onClick={() => onPick(n)}
            className={cn(
              "group flex items-center gap-3 rounded-lg border bg-white px-3 py-2.5 text-left transition-colors",
              n.verdict === "trap"
                ? "border-[#131316] shadow-[2px_3px_0_0_#131316]"
                : "border-zinc-200 hover:border-zinc-400"
            )}
          >
            <span className="w-4 shrink-0 font-mono text-[11px] font-bold text-zinc-400">
              {i + 1}
            </span>
            <span className={cn("flex h-7 w-7 shrink-0 items-center justify-center rounded-md border", TINT[n.kind])}>
              <Icon className="h-3.5 w-3.5" strokeWidth={2.25} />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[13px] font-bold text-[#131316]">{n.label}</span>
              {n.verdict === "trap" && (
                <span className="block text-[11px] font-medium text-red-600">
                  the model trusted this — it shipped 8 months ago
                </span>
              )}
              {n.verdict === "cause" && (
                <span className="block text-[11px] font-medium text-emerald-700">
                  the actual cause — ranked 4th
                </span>
              )}
            </span>
            {/* the score bar makes the 0.91-vs-0.34 gap physical */}
            <span className="hidden h-1.5 w-20 shrink-0 overflow-hidden rounded-full bg-zinc-100 sm:block">
              <span
                className="block h-full rounded-full"
                style={{
                  width: `${n.score * 100}%`,
                  backgroundColor: n.verdict === "cause" ? EMERALD : "#131316",
                }}
              />
            </span>
            <ScoreChip score={n.score} muted={n.verdict !== "trap"} />
          </button>
        );
      })}
    </div>
  );
}

/* mode B — the same retrieval, drawn as the graph it actually is */
function GraphView({
  onPick,
  selected,
}: {
  onPick: (n: XrayNode) => void;
  selected: string | null;
}) {
  return (
    // min-w keeps the layout proportional; phones swipe the canvas instead of
    // collapsing the nodes on top of each other
    <div className="overflow-x-auto pb-1">
    <div className="relative h-[300px] w-full min-w-[560px] sm:h-[330px]">
      <svg className="absolute inset-0 h-full w-full" aria-hidden="true">
        {EDGES.map((e) => {
          const a = byId(e.from);
          const b = byId(e.to);
          return (
            <line
              key={`${e.from}-${e.to}`}
              x1={`${a.x}%`}
              y1={`${a.y}%`}
              x2={`${b.x}%`}
              y2={`${b.y}%`}
              stroke={e.traced ? EMERALD : "#D4D4D8"}
              strokeWidth={e.traced ? 2 : 1.5}
              strokeDasharray={e.traced ? "5 4" : "3 4"}
              className={e.traced ? "lp-edge-flow" : undefined}
            />
          );
        })}
      </svg>

      {NODES.map((n) => {
        const Icon = ICONS[n.kind];
        const isSel = selected === n.id;
        return (
          <button
            key={n.id}
            type="button"
            onClick={() => onPick(n)}
            style={{ left: `${n.x}%`, top: `${n.y}%` }}
            className={cn(
              "absolute flex -translate-x-1/2 -translate-y-1/2 items-center gap-2 rounded-lg border bg-white px-2.5 py-1.5",
              "transition-transform duration-150 hover:scale-105",
              n.used
                ? "border-[#131316] shadow-[3px_4px_0_0_#131316]"
                : "border-zinc-300 shadow-[2px_3px_0_0_rgba(19,19,22,0.10)]",
              isSel && "scale-105 ring-2 ring-emerald-500 ring-offset-2"
            )}
          >
            <span className={cn("flex h-6 w-6 shrink-0 items-center justify-center rounded border", TINT[n.kind])}>
              <Icon className="h-3 w-3" strokeWidth={2.25} />
            </span>
            <span className="text-[11.5px] font-bold text-[#131316]">{n.label}</span>
            <ScoreChip score={n.score} muted={!n.used} />
          </button>
        );
      })}

      <span className="absolute bottom-0 left-0 rounded-md border border-[#131316] bg-white px-2 py-1 font-mono text-[10px] font-bold text-[#131316]">
        INC-2291 → payment-service ← PR #4977
      </span>
    </div>
    </div>
  );
}

export function TraceXray() {
  const [mode, setMode] = useState<"ranked" | "graph">("ranked");
  const [picked, setPicked] = useState<XrayNode | null>(null);

  return (
    <section className="border-y border-zinc-200 bg-[#FAFAFB]">
      <div className="mx-auto max-w-5xl px-5 py-20">
        <SectionHead
          eyebrow="Retrieval x-ray"
          title="The agent was confident. It was also wrong."
          sub="A real trace from the demo agent. It blamed an 8-month-old PR for today's outage — because that PR reads like the question. Here's the evidence that shows why."
        />

        <Reveal delay={0.06} className="mt-10">
          <div className={cn(CARD, "overflow-hidden shadow-[5px_6px_0_0_#131316]")}>
            {/* the wrong answer, up top */}
            <div className="border-b border-[#131316] bg-[#131316] p-4 sm:p-5">
              <p className="font-mono text-[10px] font-bold uppercase tracking-[0.25em] text-zinc-500">
                asked
              </p>
              <p className="mt-1.5 font-mono text-[12.5px] text-zinc-200">
                &quot;Why are checkout payments failing since yesterday&apos;s deploy?&quot;
              </p>
              <p className="mt-4 font-mono text-[10px] font-bold uppercase tracking-[0.25em] text-zinc-500">
                answered
              </p>
              <p className="mt-1.5 flex items-start gap-2 text-[13px] leading-relaxed text-zinc-300">
                <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-red-400" strokeWidth={2.25} />
                <span>
                  &quot;The failures look like the timeout issue addressed in{" "}
                  <span className="font-bold text-red-300">PR #4102</span> — retry logic in the
                  checkout payment authorizer. Consider re-applying that fix.&quot;
                </span>
              </p>
            </div>

            <div className="p-4 sm:p-5">
              {/* mode switch */}
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex gap-1 rounded-lg border border-[#131316] bg-white p-1">
                  {(["ranked", "graph"] as const).map((m) => (
                    <button
                      key={m}
                      type="button"
                      onClick={() => setMode(m)}
                      className={cn(
                        "rounded-md px-3 py-1.5 text-[12.5px] font-bold transition-colors",
                        mode === m ? "bg-[#131316] text-white" : "text-zinc-600 hover:bg-zinc-100"
                      )}
                    >
                      {m === "ranked" ? "Ranked by similarity" : "Traced through the graph"}
                    </button>
                  ))}
                </div>
                <p className="text-[12px] text-zinc-500">click any item to read the evidence</p>
              </div>

              <div className="mt-5">
                {mode === "ranked" ? (
                  <RankedView onPick={setPicked} />
                ) : (
                  <GraphView onPick={setPicked} selected={picked?.id ?? null} />
                )}
              </div>

              {/* the takeaway flips with the mode */}
              <div className="mt-5 rounded-lg border border-zinc-200 bg-[#FAFAFB] p-3.5">
                {mode === "ranked" ? (
                  <p className="text-[13px] leading-relaxed text-zinc-700">
                    <span className="font-bold text-[#131316]">Similarity is not causality.</span>{" "}
                    The stale PR scored <span className="font-mono font-bold">0.91</span> because it
                    shares the question&apos;s vocabulary. Yesterday&apos;s SDK bump — the real
                    cause — scored <span className="font-mono font-bold">0.34</span>, because a
                    dependency diff shares almost no words with &quot;checkout failing&quot;.
                  </p>
                ) : (
                  <p className="text-[13px] leading-relaxed text-zinc-700">
                    <span className="font-bold text-[#131316]">The path finds what ranking missed.</span>{" "}
                    The incident reports on <span className="font-mono font-bold">payment-service</span>,
                    and PR #4977 touches it. Two hops connect the outage to its cause — a flat ranked
                    list can never show that edge.
                  </p>
                )}
              </div>

              {/* inspector */}
              {picked && (
                <div className="mt-3 rounded-lg border border-[#131316] bg-white p-3.5 shadow-[2px_3px_0_0_#131316]">
                  <p className="flex items-center justify-between gap-3">
                    <span className="text-[13px] font-bold text-[#131316]">{picked.label}</span>
                    <span
                      className={cn(
                        "rounded-full border px-2 py-0.5 font-mono text-[10px] font-bold",
                        picked.used
                          ? "border-[#131316] text-[#131316]"
                          : "border-zinc-300 text-zinc-500"
                      )}
                      style={picked.used ? { backgroundColor: LIME } : undefined}
                    >
                      {picked.used ? "used in the answer" : "retrieved, unused"}
                    </span>
                  </p>
                  <p className="mt-2 font-mono text-[11.5px] leading-relaxed text-zinc-600">
                    {picked.snippet}
                  </p>
                </div>
              )}
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
