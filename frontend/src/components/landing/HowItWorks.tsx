import { ArrowRight, Braces, Radio, Scan, Waypoints } from "lucide-react";
import { cn } from "@/lib/utils";
import { CARD, EMERALD, LIME, Reveal, SectionHead } from "./_shared";

const PIPELINE = [
  { icon: Radio, title: "Callback handler", body: "Rides along on the run. No code changes to your graph." },
  { icon: Braces, title: "AgentTrace v0.2", body: "Framework-neutral JSON: spans, items, scores, edges." },
  { icon: Scan, title: "Viewer", body: "Local server, bundled UI. Nothing leaves your machine." },
];

const MECHANICS = [
  {
    icon: Radio,
    title: "One span per node, zero framework noise",
    body: "LangChain emits lifecycle events carrying run_id and parent_run_id. LangGraph wraps your nodes in its own machinery that fires the same events — so a 2-node graph would log ~10 spans of garbage.",
    detail: "keep span only when\nname === metadata.langgraph_node",
    note: "One node, one span. RunnableSequence, ChannelWrite, __start__ never reach the trace.",
  },
  {
    icon: Waypoints,
    title: "Two arms: lexical seeds, then 1-hop expansion",
    body: "Half the budget goes to items that match the query directly. The rest is pulled in structurally — the author of a matched PR, the issue it resolves, the service it touches.",
    detail: "seeds = topK(score, k/2)\nrest  = neighbors(seeds.edges)",
    note: "Structural neighbors keep their own (often lower) score — nothing inherits relevance it didn't earn.",
  },
  {
    icon: Scan,
    title: "Retrieved vs. used — where the budget actually goes",
    body: "After the run, each retrieved item is compared against the final answer. Items that surfaced render highlighted; items retrieved and ignored render dimmed.",
    detail: "overlap = |item ∩ answer|\n          / min(|item|, |answer|)",
    note: "A lexical heuristic, labeled as one — threshold 0.2. It is never presented as a model-computed relevance judgment.",
  },
];

/* the honest context story: not "we cut tokens N×", but "here is the waste,
   now you can see it" */
function ContextBudget() {
  const rows = [
    { label: "PR #4102", pct: 34, used: true },
    { label: "INC-2291", pct: 22, used: false },
    { label: "payment-service", pct: 18, used: false },
    { label: "PR #4977", pct: 16, used: false },
    { label: "Lena K.", pct: 10, used: false },
  ];
  return (
    <div className="flex flex-col gap-2">
      {rows.map((r) => (
        <div key={r.label} className="flex items-center gap-3">
          <span className="w-28 shrink-0 truncate font-mono text-[11px] text-zinc-500">
            {r.label}
          </span>
          <span className="h-4 flex-1 overflow-hidden rounded border border-zinc-200 bg-white">
            <span
              className="block h-full"
              style={{
                width: `${r.pct}%`,
                backgroundColor: r.used ? EMERALD : "#E4E4E7",
              }}
            />
          </span>
          <span
            className={cn(
              "w-24 shrink-0 text-right font-mono text-[10px] font-bold",
              r.used ? "text-emerald-700" : "text-zinc-400"
            )}
          >
            {r.used ? "in the answer" : "unused"}
          </span>
        </div>
      ))}
    </div>
  );
}

export function HowItWorks() {
  return (
    <section className="mx-auto max-w-6xl px-5 py-20">
      <SectionHead
        eyebrow="How it works"
        title="Evidence, not vibes."
        sub="Three mechanics do all the work. None of them call an LLM, and none of them invent a number."
      />

      {/* pipeline strip */}
      <Reveal delay={0.05} className="mt-12">
        <div className="flex flex-col items-stretch gap-3 sm:flex-row">
          {PIPELINE.map((p, i) => (
            <div key={p.title} className="flex min-w-0 flex-1 items-stretch gap-3">
              <div className={cn(CARD, "min-w-0 flex-1 p-4")}>
                <p.icon className="h-5 w-5 text-emerald-600" strokeWidth={2.25} />
                <p className="mt-2.5 text-[14px] font-bold text-[#131316]">{p.title}</p>
                <p className="mt-1 text-[12.5px] leading-relaxed text-zinc-600">{p.body}</p>
              </div>
              {i < PIPELINE.length - 1 && (
                <ArrowRight
                  className="hidden h-5 w-5 shrink-0 self-center text-zinc-400 sm:block"
                  strokeWidth={2.25}
                />
              )}
            </div>
          ))}
        </div>
      </Reveal>

      {/* the three mechanics */}
      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-3">
        {MECHANICS.map((m, i) => (
          <Reveal key={m.title} delay={0.06 * (i + 1)} className="h-full min-w-0">
            <div className={cn(CARD, "flex h-full flex-col p-5")}>
              <m.icon className="h-6 w-6 text-[#131316]" strokeWidth={2.25} />
              <h3 className="mt-3 text-[15.5px] font-bold leading-snug text-[#131316]">{m.title}</h3>
              <p className="mt-2 text-[13px] leading-relaxed text-zinc-600">{m.body}</p>
              <pre className="mt-3.5 whitespace-pre-wrap break-words rounded-lg border border-zinc-700 bg-[#131316] px-3 py-2.5 font-mono text-[11px] leading-relaxed text-emerald-300">
                {m.detail}
              </pre>
              <p className="mt-auto pt-3 text-[12px] leading-relaxed text-zinc-500">{m.note}</p>
            </div>
          </Reveal>
        ))}
      </div>

      {/* context budget — the honest token story */}
      <Reveal delay={0.1} className="mt-5">
        <div className={cn(CARD, "grid grid-cols-1 gap-6 p-5 sm:p-6 lg:grid-cols-[1fr_1.1fr]")}>
          <div className="min-w-0">
            <h3 className="font-display text-xl font-bold text-[#131316]">
              Stop paying for context the answer{" "}
              <span className="inline-block -rotate-1 rounded-lg px-2" style={{ backgroundColor: LIME }}>
                never read
              </span>
            </h3>
            <p className="mt-3 text-[13.5px] leading-relaxed text-zinc-600">
              Whole-repo stuffing sends every plausible file and hopes. Graph retrieval sends a
              scoped set of items plus the edges between them — and Graphsight shows you which of
              those the answer actually leaned on.
            </p>
            <p className="mt-3 text-[13.5px] leading-relaxed text-zinc-600">
              In the trace above, five items were retrieved and{" "}
              <span className="font-bold text-[#131316]">one carried the answer</span>. The other
              four are budget you paid for and can now see. That is the lever: not a magic
              compression ratio, but visible waste you can cut on your own data.
            </p>
            <p className="mt-4 rounded-lg border border-zinc-200 bg-[#FAFAFB] p-3 text-[12px] leading-relaxed text-zinc-500">
              We publish what we measure. Our own benchmark did not show a token reduction on the
              corpus we tested — so we do not claim one. What Graphsight gives you is the
              measurement itself, per run.
            </p>
          </div>
          <div className="min-w-0">
            <p className="mb-3 font-mono text-[10px] font-bold uppercase tracking-[0.25em] text-zinc-400">
              context share · demo trace
            </p>
            <ContextBudget />
          </div>
        </div>
      </Reveal>
    </section>
  );
}
