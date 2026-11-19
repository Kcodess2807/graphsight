import { useSearchParams } from "react-router-dom";
import { Database, GitPullRequest, History, PenLine } from "lucide-react";
import { cn } from "@/lib/utils";
import { CARD, EMERALD, LIME, Reveal, SectionHead } from "./_shared";

/* ═══════════ the ledger: one fact through its whole life ═══════════ */

type Row = {
  fact: string;
  // who wrote it: the agent (with its source label) or the source system
  source: string;
  agent: boolean;
  ended?: boolean;
};

const GITHUB_ROW: Row = { fact: "PR #4821 TOUCHES checkout-service", source: "GitHub", agent: false };

// signatures match backend/tracerag/memory.py
const STEPS: { name: string; told: string; call: string; rows: Row[]; answer: string; why: string }[] = [
  {
    name: "Remember",
    told: "The payments team owns checkout-service.",
    call: 'memory.remember(\n    "checkout-service", "owned by", "payments team",\n    source="standup-12")',
    rows: [GITHUB_ROW, { fact: "checkout-service OWNED_BY payments team", source: "standup-12", agent: true }],
    answer: "payments team",
    why: "The answer cites a remembered fact and names where it came from.",
  },
  {
    name: "Update",
    told: "Ownership moved to the billing team.",
    call: 'memory.remember(\n    "checkout-service", "owned by", "billing team",\n    source="reorg-memo", replace=True)',
    rows: [
      GITHUB_ROW,
      { fact: "checkout-service OWNED_BY payments team", source: "standup-12", agent: true, ended: true },
      { fact: "checkout-service OWNED_BY billing team", source: "reorg-memo", agent: true },
    ],
    answer: "billing team",
    why: "The old fact is ended, not deleted. It stops being recalled and stays as history.",
  },
  {
    name: "Retract",
    told: "checkout-service no longer has an owner.",
    call: 'memory.retract("checkout-service", "OWNED_BY")',
    rows: [
      GITHUB_ROW,
      { fact: "checkout-service OWNED_BY payments team", source: "standup-12", agent: true, ended: true },
      { fact: "checkout-service OWNED_BY billing team", source: "reorg-memo", agent: true, ended: true },
    ],
    answer: "unknown",
    why: "Nothing replaces the fact, so the answer is unknown, not the last owner.",
  },
  {
    name: "Forget",
    told: "That first note was wrong. Delete it.",
    call: 'memory.forget("checkout-service", "OWNED_BY", "payments team")',
    rows: [
      GITHUB_ROW,
      { fact: "checkout-service OWNED_BY billing team", source: "reorg-memo", agent: true, ended: true },
    ],
    answer: "unknown",
    why: "Forget removes the agent’s own fact, history included. The GitHub fact can’t be deleted this way.",
  },
];

export function MemoryLedger() {
  // the step lives in the URL, so a link can open on "Retract"
  const [params, setParams] = useSearchParams();
  const wanted = Number(params.get("step")) - 1;
  const step = wanted >= 0 && wanted < STEPS.length ? wanted : 0;
  const setStep = (i: number) => {
    const next = new URLSearchParams(params);
    next.set("step", String(i + 1));
    setParams(next, { replace: true, preventScrollReset: true });
  };
  const s = STEPS[step];
  return (
    <section className="mx-auto max-w-6xl px-5 py-16">
      <SectionHead
        title="One fact, through its whole life"
        sub="An agent’s memory has to change when the world does. Step through what the store keeps, what it ends, and what the agent answers each time."
      />
      <Reveal className="mt-10">
        <div className={cn(CARD, "overflow-hidden shadow-[5px_6px_0_0_#131316]")}>
          {/* a real sequence, so the steps are numbered */}
          <div role="group" aria-label="Memory operations" className="grid grid-cols-2 border-b border-[#131316] sm:grid-cols-4">
            {STEPS.map((x, i) => (
              <button
                key={x.name}
                type="button"
                aria-current={i === step ? "step" : undefined}
                onClick={() => setStep(i)}
                className={cn(
                  "flex items-center gap-2 border-[#131316] px-4 py-3 text-left text-[13.5px] font-bold transition-colors duration-150",
                  // inside the card edge, which clips anything drawn outside it
                  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-600 focus-visible:-outline-offset-4",
                  i > 0 && "sm:border-l",
                  i % 2 === 1 && "max-sm:border-l",
                  i < 2 && "max-sm:border-b",
                  i === step ? "bg-[#131316] text-white" : "bg-white text-[#131316] hover:bg-emerald-50"
                )}
              >
                <span
                  className={cn(
                    "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-[#131316] font-mono text-[10.5px] text-[#131316]",
                    i === step ? "" : "bg-white"
                  )}
                  style={i === step ? { backgroundColor: LIME } : undefined}
                >
                  {i + 1}
                </span>
                {x.name}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.15fr]">
            {/* what goes in */}
            <div className="min-w-0 border-[#131316] bg-[#FAFAFB] p-5 lg:border-r">
              <p className="text-[12.5px] font-bold text-zinc-500">The agent is told</p>
              <p className="mt-1.5 text-[16px] font-semibold leading-snug text-[#131316]">&ldquo;{s.told}&rdquo;</p>
              <pre translate="no" className="mt-4 whitespace-pre-wrap break-words rounded-lg border border-zinc-700 bg-[#131316] px-3.5 py-3 font-mono text-[12px] leading-relaxed text-emerald-300">
                {s.call}
              </pre>
              <p className="mt-4 text-[12.5px] font-bold text-zinc-500">Then it is asked</p>
              <p className="mt-1.5 text-[14px] font-semibold text-[#131316]">Who owns checkout-service?</p>
              <p className="mt-2.5 inline-block rounded-lg border border-[#131316] bg-white px-3 py-1.5 font-mono text-[13px] font-bold text-[#131316] shadow-[2px_3px_0_0_#C8F169]">
                {s.answer}
              </p>
              <p className="mt-3 text-[13px] leading-relaxed text-zinc-600">{s.why}</p>
            </div>

            {/* what the store holds */}
            <div className="min-w-0 p-5">
              <p className="text-[12.5px] font-bold text-zinc-500">What the store holds</p>
              <ul aria-live="polite" className="mt-3 space-y-2.5">
                {s.rows.map((r) => (
                  <li
                    key={r.fact}
                    className={cn(
                      "rounded-lg border px-3.5 py-2.5",
                      r.ended
                        ? "border-zinc-300 bg-[#FAFAFB]"
                        : r.agent
                          ? "border-emerald-600 bg-emerald-50 shadow-[2px_3px_0_0_#059669]"
                          : "border-[#131316] bg-white"
                    )}
                  >
                    <p
                      className={cn(
                        "break-words font-mono text-[12.5px] font-bold",
                        r.ended ? "text-zinc-500 line-through" : "text-[#131316]"
                      )}
                    >
                      {r.fact}
                    </p>
                    <p className="mt-1 text-[12px] text-zinc-600">
                      {r.agent ? `remembered, source: ${r.source}` : "read from GitHub"}
                      {r.ended && <span className="font-bold text-zinc-700"> · ended, kept as history</span>}
                      {!r.ended && r.agent && <span className="font-bold text-emerald-700"> · live</span>}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </Reveal>
    </section>
  );
}

/* ═══════════════════ three kinds of memory ═══════════════════════ */

const KINDS = [
  {
    icon: GitPullRequest,
    name: "Source memory",
    where: "clone to use",
    body: "PRs, issues, people and files, read from GitHub and linked by typed relations. The agent can read it and never rewrite it.",
    example: "PR #4821 RESOLVES Issue #982",
  },
  {
    icon: History,
    name: "Episodic memory",
    where: "install from PyPI",
    body: "Every run is saved with its outcome. A later run recalls past successful runs on the same subject and uses them as evidence.",
    example: 'recall("who owns checkout?")',
  },
  {
    icon: PenLine,
    name: "Agent facts",
    where: "experimental, clone to use",
    body: "What the agent learns in conversation, stored as facts in the same graph. Each one carries its source and can be replaced, retracted or forgotten.",
    example: "checkout-service OWNED_BY billing team",
  },
];

export function MemoryKinds() {
  return (
    <section className="border-y border-zinc-200 bg-[#FAFAFB]">
      <div className="mx-auto max-w-6xl px-5 py-20">
        <SectionHead
          title="Three kinds of memory in one store"
          sub="They stay labelled all the way to the prompt, so the model always knows a fact it was told from a fact the repo records."
        />
        <div className="mt-12 grid grid-cols-1 gap-5 md:grid-cols-3">
          {KINDS.map((k, i) => (
            <Reveal key={k.name} delay={i * 0.07} className="h-full">
              <div className={cn(CARD, "flex h-full flex-col p-5")}>
                <div className="flex items-center justify-between">
                  <k.icon aria-hidden="true" className="h-6 w-6 text-[#131316]" strokeWidth={2.25} />
                  <span className="rounded-full border border-[#131316] bg-white px-2 py-0.5 text-[11px] font-bold text-[#131316]">
                    {k.where}
                  </span>
                </div>
                <h3 className="mt-3 font-display text-xl font-bold text-[#131316]">{k.name}</h3>
                <p className="mt-2 text-[13.5px] leading-relaxed text-zinc-600">{k.body}</p>
                <p className="mt-auto break-words pt-4 font-mono text-[12px] font-bold text-emerald-700">{k.example}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ═══════════ results: the numbers in backend/eval/results ═══════════ */

type Bar = { label: string; value: number; ours?: boolean };

function Bars({ title, note, total, bars }: { title: string; note: string; total: number; bars: Bar[] }) {
  return (
    <div className={cn(CARD, "h-full p-5 sm:p-6")}>
      <h3 className="font-display text-xl font-bold text-[#131316]">{title}</h3>
      <p className="mt-1.5 text-[13px] leading-relaxed text-zinc-600">{note}</p>
      <dl className="mt-5 space-y-3">
        {bars.map((b) => (
          <div key={b.label} className="grid grid-cols-[7.5rem_1fr_3.5rem] items-center gap-3">
            <dt className={cn("text-[13px]", b.ours ? "font-bold text-[#131316]" : "text-zinc-600")}>{b.label}</dt>
            <span className="h-5 overflow-hidden rounded border border-[#131316] bg-white" aria-hidden="true">
              <span
                className="block h-full"
                style={{ width: `${(b.value / total) * 100}%`, backgroundColor: b.ours ? EMERALD : "#D4D4D8" }}
              />
            </span>
            <dd className="text-right font-mono text-[13px] font-bold text-[#131316]">
              {b.value}/{total}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function Results() {
  return (
    <section className="mx-auto max-w-6xl px-5 py-20">
      <SectionHead
        title="Measured, with the misses left in"
        sub="Tasks were written and committed before any run, and graded by exact match with no LLM judge. The memory facts are invented and written by the author. Every result file is in the repo."
      />
      <div className="mt-12 grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Reveal className="h-full">
          <Bars
            title="Does memory change the answer?"
            note="22 held-out tasks on pytest-dev/pytest: new facts, changed facts, retractions, and facts never stated."
            total={22}
            bars={[
              { label: "No memory", value: 5 },
              { label: "Episodic recall", value: 14 },
              { label: "Graph memory", value: 16, ours: true },
            ]}
          />
        </Reveal>
        <Reveal delay={0.07} className="h-full">
          <Bars
            title="Does the graph find the right thing?"
            note="175 retrieval tasks over pallets/click and pytest-dev/pytest, same model and prompt for every retriever."
            total={175}
            bars={[
              { label: "Whole repo in prompt", value: 171 },
              { label: "Vector search", value: 88 },
              { label: "Keyword (BM25)", value: 155 },
              { label: "Graph", value: 154, ours: true },
            ]}
          />
        </Reveal>
      </div>
      <Reveal delay={0.1} className="mt-5">
        <div className={cn(CARD, "grid grid-cols-1 gap-5 p-5 sm:p-6 md:grid-cols-[auto_1fr] md:items-center")}>
          <p className="flex items-center gap-3">
            <Database aria-hidden="true" className="h-6 w-6 shrink-0 text-emerald-700" strokeWidth={2.25} />
            <span className="font-display text-xl font-bold text-[#131316]">
              0 of 20 planted wrong memories were followed
            </span>
          </p>
          <p className="text-[13.5px] leading-relaxed text-zinc-600">
            Putting the whole snapshot in the prompt beat every retriever, because these repos
            are small enough to fit. The graph ties keyword search and beats vector search, and
            ties episodic recall on memory. Nothing here is measured at a size where retrieval
            is required.{" "}
            <a
              href="https://github.com/Kcodess2807/graphsight/tree/main/backend/eval"
              target="_blank"
              rel="noreferrer"
              className="font-bold text-emerald-700 underline-offset-2 hover:underline"
            >
              Read the eval
            </a>
          </p>
        </div>
      </Reveal>
    </section>
  );
}
