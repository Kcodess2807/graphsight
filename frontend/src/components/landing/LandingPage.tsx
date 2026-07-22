import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Brain,
  Check,
  Cloud,
  Coins,
  GitBranch,
  GitPullRequest,
  Github,
  ListTodo,
  MousePointer2,
  Route,
  Terminal,
  Ticket,
  Webhook,
  Wind,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";

// one-line rebrand if the product name changes
const BRAND = "Graphsight";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// ── light neubrutalist system, no purple ───────────────────────────
// white page · #131316 ink · BLACK primary buttons · lime #C8F169
// marker-highlights · emerald interactive accents · multicolor icons
const CARD =
  "rounded-xl border border-[#131316] bg-white shadow-[3px_4px_0_0_#131316]";
const BTN_PRIMARY =
  "rounded-lg bg-[#131316] font-semibold text-white transition-colors duration-150 hover:bg-black focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#131316]";
const LIME = "#C8F169";
const EMERALD = "#059669";

/* ═══════════════════════ shared pieces ═══════════════════════════ */

function Reveal({
  children,
  delay = 0,
  className,
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.15 }}
      transition={{ duration: 0.45, delay, ease: "easeOut" }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

function scrollToForm() {
  document.getElementById("waitlist")?.scrollIntoView({ behavior: "smooth", block: "center" });
}

function SectionHead({
  eyebrow,
  title,
  sub,
}: {
  eyebrow?: string;
  title: string;
  sub?: string;
}) {
  return (
    <Reveal className="mx-auto max-w-2xl text-center">
      {eyebrow && (
        <p className="text-xs font-bold uppercase tracking-[0.2em] text-emerald-600">{eyebrow}</p>
      )}
      <h2 className="mt-3 font-display text-3xl font-bold leading-tight tracking-[-0.02em] text-[#131316] sm:text-4xl">
        {title}
      </h2>
      {sub && <p className="mt-3 text-[15px] leading-relaxed text-zinc-600">{sub}</p>}
    </Reveal>
  );
}

function WaitlistForm({ inputId, center }: { inputId: string; center?: boolean }) {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [shakeNonce, setShakeNonce] = useState(0);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!EMAIL_RE.test(email.trim())) {
      setError("Enter a valid work email.");
      setShakeNonce((n) => n + 1);
      return;
    }
    // TODO: POST to your form backend (Formspree/Loops/Tally) here
    console.log(`[${BRAND} waitlist]`, email.trim());
    setError(null);
    setDone(true);
  };

  if (done) {
    return (
      <div
        aria-live="polite"
        className={cn("flex items-center gap-2 py-2.5 text-sm text-zinc-700", center && "justify-center")}
      >
        <motion.span
          initial={{ opacity: 0, scale: 0.85 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
          className="flex items-center gap-2 font-medium"
        >
          <span className="flex h-[18px] w-[18px] items-center justify-center rounded-full bg-emerald-500">
            <Check className="h-3 w-3 text-white" strokeWidth={2.5} />
          </span>
          You&apos;re on the list. We&apos;ll be in touch soon.
        </motion.span>
      </div>
    );
  }

  return (
    <div className={cn("w-full max-w-md", center && "mx-auto")}>
      <form onSubmit={submit} noValidate className="flex flex-col gap-2.5 sm:flex-row">
        <label htmlFor={inputId} className="sr-only">
          Work email
        </label>
        <input
          id={inputId}
          key={shakeNonce}
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@company.com"
          autoComplete="email"
          spellCheck={false}
          className={cn(
            "w-full flex-1 rounded-lg border border-[#131316] bg-white px-3.5 py-2.5 text-sm text-[#131316]",
            "placeholder:text-zinc-400 transition-shadow duration-150",
            "focus:outline-none focus:shadow-[3px_4px_0_0_#059669]",
            shakeNonce > 0 && error && "lp-shake"
          )}
        />
        <button
          type="submit"
          className={cn(BTN_PRIMARY, "shrink-0 px-4 py-2.5 text-sm shadow-[3px_4px_0_0_#C8F169]")}
        >
          Join the waitlist
        </button>
      </form>
      <div aria-live="polite" className="mt-2 text-[13px] font-medium text-red-500">
        {error}
      </div>
      <p className={cn("mt-2 text-xs text-zinc-500", center && "text-center")}>
        Free for early teams · No credit card · Unsubscribe anytime
      </p>
    </div>
  );
}

/* copyable shell command, terminal-styled */
function CopyCommand({ command, compact }: { command: string; compact?: boolean }) {
  const [copied, setCopied] = useState(false);
  const copy = useCallback(() => {
    navigator.clipboard?.writeText(command).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    });
  }, [command]);
  return (
    <button
      type="button"
      onClick={copy}
      aria-label={`Copy command: ${command}`}
      className={cn(
        "group flex w-full items-center justify-between gap-3 rounded-lg border border-zinc-700 bg-[#131316] text-left font-mono text-zinc-100 transition-colors duration-150 hover:border-zinc-500",
        compact ? "px-3.5 py-2 text-[12.5px]" : "px-4 py-3 text-[13px]"
      )}
    >
      <span className="truncate">
        <span className="text-zinc-500">$ </span>
        {command}
      </span>
      <span className="shrink-0 text-[10.5px] font-bold uppercase tracking-wide text-zinc-500 transition-colors duration-150 group-hover:text-lime-300">
        {copied ? "copied" : "copy"}
      </span>
    </button>
  );
}

/* ═══════════════════════ hero ════════════════════════════════════ */

/* floating hard-shadow sticker, rotation on the wrapper so the bob
   animation's translate doesn't overwrite it */
function Sticker({
  className,
  delay = 0,
  children,
}: {
  className: string;
  delay?: number;
  children: ReactNode;
}) {
  return (
    <div className={cn("absolute", className)}>
      <div className="lp2-float" style={{ animationDelay: `${delay}s` }}>
        {children}
      </div>
    </div>
  );
}

function Hero() {
  return (
    <section className="relative overflow-hidden">
      <div className="lp2-dots-light pointer-events-none absolute inset-0" aria-hidden="true" />

      <div className="relative mx-auto max-w-6xl px-5 pb-20 pt-28 sm:pt-32">
        {/* side stickers — the product, scattered like desk notes (lg+) */}
        <div className="pointer-events-none absolute inset-0 hidden lg:block" aria-hidden="true">
          <Sticker className="left-4 top-36 -rotate-6 xl:left-10">
            <div className="flex items-center gap-2.5 rounded-xl border border-[#131316] bg-white px-3.5 py-2.5 shadow-[3px_4px_0_0_#131316]">
              <GitPullRequest className="h-4 w-4 text-emerald-600" strokeWidth={2.25} />
              <div className="leading-tight">
                <p className="text-[12.5px] font-bold text-[#131316]">PR #4821</p>
                <p className="text-[10.5px] text-zinc-500">merged · checkout fix</p>
              </div>
            </div>
          </Sticker>

          <Sticker className="bottom-32 left-16 rotate-3 xl:left-24" delay={0.8}>
            <svg width="44" height="44" viewBox="0 0 24 24" aria-hidden="true">
              <path
                d="M12 2l2.5 7L22 12l-7.5 3L12 22l-2.5-7L2 12l7.5-3z"
                fill={LIME}
                stroke="#131316"
                strokeWidth="1.25"
                strokeLinejoin="round"
              />
            </svg>
          </Sticker>

          <Sticker className="right-4 top-36 rotate-6 xl:right-10" delay={0.4}>
            <span
              className="flex items-center gap-1.5 rounded-full border border-[#131316] px-3.5 py-2 text-[13px] font-bold text-[#131316] shadow-[3px_4px_0_0_#131316]"
              style={{ backgroundColor: LIME }}
            >
              <Zap className="h-4 w-4" strokeWidth={2.5} />
              49ms recall
            </span>
          </Sticker>

          <Sticker className="bottom-28 right-8 -rotate-3 xl:right-16" delay={1.2}>
            <div className="flex items-center gap-2 rounded-xl border border-[#131316] bg-white px-3.5 py-2.5 shadow-[3px_4px_0_0_#131316]">
              <Ticket className="h-4 w-4 text-sky-500" strokeWidth={2.25} />
              <p className="text-[12px] font-bold text-[#131316]">
                JIRA-982 <span className="text-zinc-400">→</span> PR #4821
              </p>
            </div>
          </Sticker>
        </div>

        {/* centered copy */}
        <div className="relative mx-auto max-w-3xl text-center">
          <Reveal>
            <span className="inline-flex items-center gap-2 rounded-full border border-[#131316] bg-white py-1 pl-1.5 pr-3.5 text-[13px] font-medium text-zinc-700 shadow-[2px_3px_0_0_#131316]">
              <span
                className="rounded-full px-2 py-0.5 text-[11px] font-bold text-[#131316]"
                style={{ backgroundColor: LIME }}
              >
                NEW
              </span>
              Introducing the {BRAND} memory graph
            </span>
          </Reveal>

          <Reveal delay={0.06}>
            <h1 className="mt-7 font-display text-[clamp(2.5rem,6vw,4.25rem)] font-bold leading-[1.06] tracking-[-0.02em] text-[#131316]">
              <span
                className="inline-block -rotate-1 rounded-xl px-3"
                style={{ backgroundColor: LIME }}
              >
                Graph memory
              </span>{" "}
              for your AI coding agents
            </h1>
          </Reveal>

          <Reveal delay={0.12}>
            <p className="mx-auto mt-6 max-w-xl text-[16px] leading-[1.65] text-zinc-600">
              {BRAND} maps your GitHub PRs, Jira tickets, and codebase into a live
              knowledge graph — served to Claude Code and Cursor over MCP, so your
              agents stop guessing code history.
            </p>
          </Reveal>

          <Reveal delay={0.18} className="mt-9 flex justify-center">
            <div id="waitlist" className="w-full max-w-md scroll-mt-28">
              <WaitlistForm inputId="email-hero" center />
            </div>
          </Reveal>

          <Reveal delay={0.24} className="mx-auto mt-6 flex max-w-md flex-col items-center gap-2.5">
            <CopyCommand compact command="pip install graphsight" />
            <p className="text-[13px] font-medium text-zinc-500">
              already on PyPI ·{" "}
              <Link
                to="/memory/preview"
                className="font-bold text-emerald-700 underline-offset-2 hover:underline"
              >
                try the live demo →
              </Link>
            </p>
          </Reveal>
        </div>
      </div>
    </section>
  );
}

/* ══════════ tilted logo marquee (two rows, opposite drift) ═══════ */

const MARQUEE_ITEMS = [
  { icon: Terminal, label: "Claude Code" },
  { icon: MousePointer2, label: "Cursor" },
  { icon: Wind, label: "Windsurf" },
  { icon: Github, label: "GitHub" },
  { icon: Ticket, label: "Jira" },
  { icon: ListTodo, label: "Linear" },
  { icon: Webhook, label: "Webhooks" },
  { icon: GitBranch, label: "MCP" },
];

function MarqueeRow({ reverse }: { reverse?: boolean }) {
  // items duplicated once so the -50% translate loops seamlessly
  const items = [...MARQUEE_ITEMS, ...MARQUEE_ITEMS];
  return (
    <div className={cn("flex w-max items-center gap-10 py-3.5 pr-10", "lp2-marquee", reverse && "lp2-marquee-rev")}>
      {items.map((item, i) => (
        <span key={`${item.label}-${i}`} className="flex shrink-0 items-center gap-2.5">
          <item.icon className="h-5 w-5 text-[#131316]" strokeWidth={2.25} />
          <span className="text-lg font-bold uppercase tracking-tight text-[#131316]">
            {item.label}
          </span>
        </span>
      ))}
    </div>
  );
}

function Marquee() {
  return (
    <section className="relative -mx-2 overflow-hidden py-10" aria-label="Works with">
      <div className="-rotate-2">
        <div className="overflow-hidden border-y border-[#131316] bg-white">
          <MarqueeRow />
        </div>
      </div>
      <div className="-mt-1 rotate-1">
        <div className="overflow-hidden border-y border-[#131316] bg-white">
          <MarqueeRow reverse />
        </div>
      </div>
    </section>
  );
}

/* ═══════════════ code showcase (kept element) ════════════════════ */

const USE_CASE_ITEMS = [
  { title: "Causal bug tracing", body: "Which PR caused this regression, and who reviewed it?" },
  { title: "Ownership queries", body: "Who owns checkout-service and what changed last week?" },
  { title: "Impact analysis", body: "What breaks if we bump the stripe SDK?" },
  { title: "Session recall", body: "Pick any past trace back up with zero re-indexing." },
];

function CodeShowcase() {
  const [active, setActive] = useState(0);
  return (
    <section className="mx-auto max-w-6xl px-5 py-16">
      <Reveal>
        <div className={cn(CARD, "grid grid-cols-1 overflow-hidden shadow-[5px_6px_0_0_#131316] md:grid-cols-[320px_1fr]")}>
          {/* use-case list */}
          <div className="space-y-2 border-[#131316] bg-[#FAFAFB] p-4 md:border-r">
            {USE_CASE_ITEMS.map((item, i) => (
              <button
                key={item.title}
                type="button"
                onClick={() => setActive(i)}
                className={cn(
                  "block w-full rounded-lg border p-3.5 text-left transition-all duration-150",
                  i === active
                    ? "border-emerald-600 bg-emerald-50 shadow-[2px_3px_0_0_#059669]"
                    : "border-transparent hover:border-zinc-300 hover:bg-white"
                )}
              >
                <p className="text-[13.5px] font-bold text-[#131316]">{item.title}</p>
                <p className="mt-1 text-[12.5px] leading-relaxed text-zinc-600">{item.body}</p>
              </button>
            ))}
          </div>

          {/* dark terminal — stays dark for contrast */}
          <div className="overflow-x-auto bg-[#0E0E10] p-5 font-mono text-[12.5px] leading-[1.85]">
            <div className="mb-3 flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full bg-[#FF5F57]" />
              <span className="h-2.5 w-2.5 rounded-full bg-[#FEBC2E]" />
              <span className="h-2.5 w-2.5 rounded-full bg-[#28C840]" />
              <span className="ml-2 text-[10px] text-zinc-500">zsh</span>
            </div>
            <p className="text-zinc-400">
              <span className="text-zinc-600">$</span> claude mcp add graphsight{" "}
              <span className="text-[#6EE7B7]">https://mcp.graphsight.dev/v1</span>
            </p>
            <p className="text-emerald-400">✓ graphsight connected · 128,406 nodes</p>
            <p aria-hidden="true">&nbsp;</p>
            <p className="text-zinc-600">{"//"} ask anything with full history</p>
            <p className="text-zinc-300">
              <span className="text-zinc-600">$</span> claude{" "}
              <span className="text-[#7DD3FC]">
                &quot;{USE_CASE_ITEMS[active].body.toLowerCase().replace(/\?$/, "")}?&quot;
              </span>
            </p>
            <p aria-hidden="true">&nbsp;</p>
            <p className="text-zinc-400">
              → <span className="text-[#38BDF8]">query_graph</span>(&quot;checkout regression&quot;)
            </p>
            <p className="pl-4 text-zinc-300">
              <span className="text-[#7DD3FC]">PR #4821</span> → checkout-service →{" "}
              <span className="text-[#7DD3FC]">JIRA-982</span>
            </p>
            <p className="pl-4 text-zinc-500">
              traced in <span className="text-emerald-400">49ms</span> · 3 hops · confidence 0.94
            </p>
          </div>
        </div>
      </Reveal>
    </section>
  );
}

/* ═══════════════════════ stats band ══════════════════════════════ */

function Stats() {
  const stats = [
    { value: "49ms", label: "Median trace latency" },
    { value: "70×", label: "Fewer LLM tokens per query" },
    { value: "100%", label: "Deterministic recall paths" },
  ];
  return (
    <section className="border-y border-zinc-200 bg-[#FAFAFB]">
      <div className="mx-auto grid max-w-5xl grid-cols-1 gap-10 px-5 py-14 text-center sm:grid-cols-3">
        {stats.map((s, i) => (
          <Reveal key={s.label} delay={i * 0.06}>
            <p className="font-display text-5xl font-bold tracking-tight text-[#131316]">{s.value}</p>
            <p className="mt-2 text-[14px] font-medium text-zinc-600">{s.label}</p>
          </Reveal>
        ))}
      </div>
    </section>
  );
}

/* ══════════ use-case bento (kept element) ════════════════════════ */

function SourceCards() {
  return (
    <div className="space-y-3">
      {[
        { icon: GitPullRequest, tint: "bg-emerald-500", label: "GitHub App", sub: "PRs, commits, reviews" },
        { icon: Ticket, tint: "bg-sky-500", label: "Jira webhooks", sub: "tickets, sprints, links" },
      ].map((c) => (
        <div key={c.label} className="rounded-lg border border-zinc-200 bg-[#FAFAFB] p-3">
          <div className="mb-2.5 space-y-1.5">
            <div className="h-1.5 w-24 rounded-full bg-zinc-300" />
            <div className="h-1.5 w-32 rounded-full bg-zinc-200" />
          </div>
          <div className="flex items-center gap-2">
            <span className={cn("flex h-6 w-6 items-center justify-center rounded-full", c.tint)}>
              <c.icon className="h-3 w-3 text-white" />
            </span>
            <div>
              <p className="text-[12.5px] font-bold text-[#131316]">{c.label}</p>
              <p className="text-[11.5px] text-zinc-500">{c.sub}</p>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function LogFeed() {
  return (
    <div className="space-y-3">
      {[
        { time: "14:23:45", tag: "INFO", tint: "bg-sky-500", text: "Webhook received — PR #4821 merged into main." },
        { time: "14:23:47", tag: "TRACE", tint: "bg-emerald-500", text: "Graph updated — 12 new edges, 3 entities linked." },
      ].map((l) => (
        <div key={l.time} className="flex gap-2.5 rounded-lg border border-zinc-200 bg-[#FAFAFB] p-3">
          <span className={cn("mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full", l.tint)}>
            <Webhook className="h-2.5 w-2.5 text-white" />
          </span>
          <div className="min-w-0">
            <p className="font-mono text-[11px] font-bold text-[#131316]">
              [{l.time}] {l.tag}
            </p>
            <p className="mt-0.5 text-[12px] leading-relaxed text-zinc-600">{l.text}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

function AgentRadar() {
  const chips = [
    { label: "Claude Code", x: "20%", y: "22%", tint: "bg-orange-500" },
    { label: "Cursor", x: "76%", y: "34%", tint: "bg-sky-500" },
    { label: "Windsurf", x: "62%", y: "78%", tint: "bg-teal-500" },
  ];
  return (
    <div className="relative mx-auto h-44 w-full">
      <div className="lp2-radar-fade absolute inset-0">
        {[0, 16, 32].map((inset) => (
          <div
            key={inset}
            className="absolute rounded-full border border-zinc-300"
            style={{ inset: `${inset}%` }}
          />
        ))}
      </div>
      {chips.map((c) => (
        <span
          key={c.label}
          style={{ left: c.x, top: c.y }}
          className="absolute flex -translate-x-1/2 -translate-y-1/2 items-center gap-1.5 rounded-md border border-[#131316] bg-white px-2 py-1 text-[11px] font-bold text-[#131316] shadow-[2px_2px_0_0_#131316]"
        >
          <span className={cn("h-2 w-2 rounded-full", c.tint)} />
          {c.label}
        </span>
      ))}
      <span className="absolute left-1/2 top-1/2 flex -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-lg bg-[#131316] p-2 shadow-[2px_3px_0_0_#C8F169]">
        <GitBranch className="h-4 w-4 text-white" />
      </span>
    </div>
  );
}

const USE_CASES = [
  {
    title: "Connect your sources",
    body: "GitHub and Jira stream PRs, tickets, and commits into the graph in real time.",
    art: <SourceCards />,
  },
  {
    title: "Watch memory form",
    body: "Every event becomes entities and edges — inspect exactly what your agents will see.",
    art: <LogFeed />,
  },
  {
    title: "One graph, every agent",
    body: "Claude Code, Cursor, and Windsurf tap the same shared memory over MCP.",
    art: <AgentRadar />,
  },
];

function UseCases() {
  return (
    <section className="mx-auto max-w-6xl px-5 py-20">
      <SectionHead
        eyebrow="Use cases"
        title="Show your agents how the codebase actually evolved."
      />
      <div className="mt-12 grid grid-cols-1 gap-5 md:grid-cols-3">
        {USE_CASES.map((u, i) => (
          <Reveal key={u.title} delay={i * 0.07} className="h-full">
            <div className={cn(CARD, "flex h-full flex-col p-5")}>
              <div className="flex-1">{u.art}</div>
              <h3 className="mt-5 text-[16px] font-bold text-[#131316]">{u.title}</h3>
              <p className="mt-1.5 text-[13.5px] leading-relaxed text-zinc-600">{u.body}</p>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  );
}

/* ════════ benefits — inspo layout: integrate + collab + grid ═════ */

const INTEGRATION_TILES = [
  { icon: Github, bg: "#131316" },
  { icon: Zap, bg: "#10B981" },
  { icon: Ticket, bg: "#0EA5E9" },
  { icon: GitBranch, bg: "#F97316" },
  { icon: Webhook, bg: "#EC4899" },
];

function IntegrateCard() {
  return (
    <div className={cn(CARD, "flex h-full flex-col overflow-hidden")}>
      <div className="p-6 pb-4">
        <h3 className="font-display text-xl font-bold text-[#131316]">Integrate with everything</h3>
        <p className="mt-2 max-w-lg text-[13.5px] leading-relaxed text-zinc-600">
          GitHub, Jira, and every MCP-compatible agent out of the box. One graph,
          zero glue code — new sources land as first-class graph entities.
        </p>
      </div>
      <div className="mt-auto grid grid-cols-3 border-t border-[#131316] sm:grid-cols-6">
        {INTEGRATION_TILES.map((t, i) => (
          <div
            key={i}
            className={cn(
              "flex h-20 items-center justify-center border-[#131316]",
              i > 0 && "border-l max-sm:[&:nth-child(4)]:border-l-0 max-sm:[&:nth-child(-n+3)]:border-b"
            )}
            style={{ backgroundColor: t.bg }}
          >
            <t.icon className="h-6 w-6 text-white" strokeWidth={2} />
          </div>
        ))}
        <div className="flex h-20 items-center justify-center border-l border-[#131316] bg-white">
          <p className="px-2 text-center text-[12px] font-bold text-[#131316]">every MCP client</p>
        </div>
      </div>
    </div>
  );
}

function CollabCard() {
  const cursors = [
    { name: "Priya", x: "14%", y: "18%", tint: "text-sky-500", chip: "border-sky-300 bg-sky-50" },
    { name: "Marcus", x: "66%", y: "12%", tint: "text-emerald-500", chip: "border-emerald-300 bg-emerald-50" },
    { name: "Ana", x: "58%", y: "62%", tint: "text-orange-500", chip: "border-orange-300 bg-orange-50" },
  ];
  return (
    <div className={cn(CARD, "flex h-full flex-col overflow-hidden")}>
      <div className="relative h-44 border-b border-[#131316] bg-[#FAFAFB]">
        {/* center trace node */}
        <span className="absolute left-1/2 top-1/2 flex -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-xl border border-[#131316] bg-white p-2.5 shadow-[2px_3px_0_0_#131316]">
          <GitPullRequest className="h-5 w-5 text-[#131316]" strokeWidth={2} />
        </span>
        {cursors.map((c) => (
          <span key={c.name} className="absolute" style={{ left: c.x, top: c.y }}>
            <MousePointer2 className={cn("h-4 w-4", c.tint)} fill="currentColor" strokeWidth={1} />
            <span
              className={cn(
                "ml-3 mt-0.5 inline-block rounded-md border px-1.5 py-0.5 text-[10.5px] font-bold text-[#131316]",
                c.chip
              )}
            >
              {c.name}
            </span>
          </span>
        ))}
      </div>
      <div className="p-6">
        <h3 className="font-display text-xl font-bold text-[#131316]">One memory, whole team</h3>
        <p className="mt-2 text-[13.5px] leading-relaxed text-zinc-600">
          Everyone&apos;s agents share the same graph — no per-laptop indexes drifting
          out of sync.
        </p>
      </div>
    </div>
  );
}

const BENEFITS = [
  { icon: Brain, tint: "text-emerald-500", title: "The External Brain", body: "Agents query the graph instead of re-reading your repo." },
  { icon: GitBranch, tint: "text-sky-500", title: "Causal Tracing", body: "Exact ticket → PR → function chains for every change." },
  { icon: Cloud, tint: "text-orange-500", title: "Zero Local Setup", body: "Managed cloud graph. Nothing to index on laptops." },
  { icon: Webhook, tint: "text-pink-500", title: "Live Webhooks", body: "Events land in the graph seconds after they happen." },
  { icon: Route, tint: "text-teal-500", title: "Deterministic Recall", body: "Every answer ships with its traced path and confidence." },
  { icon: Coins, tint: "text-amber-500", title: "70× Token Savings", body: "Graph queries replace full-repo context stuffing." },
];

function Benefits() {
  return (
    <section className="border-y border-zinc-200 bg-[#FAFAFB]">
      <div className="mx-auto max-w-6xl px-5 py-20">
        <SectionHead
          eyebrow="Why Graphsight"
          title="The clear benefits of a memory layer."
          sub="Features are good — a team whose agents stop hallucinating is better."
        />

        {/* row 1: wide integrate card + tall collab card */}
        <div className="mt-12 grid grid-cols-1 gap-5 lg:grid-cols-3">
          <Reveal className="lg:col-span-2">
            <IntegrateCard />
          </Reveal>
          <Reveal delay={0.07}>
            <CollabCard />
          </Reveal>
        </div>

        {/* row 2: small benefit cards, colored icons */}
        <div className="mt-5 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {BENEFITS.map((b, i) => (
            <Reveal key={b.title} delay={(i % 3) * 0.06} className="h-full">
              <div className={cn(CARD, "h-full p-5 transition-transform duration-150 hover:-translate-y-1")}>
                <b.icon className={cn("h-6 w-6", b.tint)} strokeWidth={2.25} />
                <h3 className="mt-3 text-[16px] font-bold text-[#131316]">{b.title}</h3>
                <p className="mt-1.5 text-[13.5px] leading-relaxed text-zinc-600">{b.body}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ═══════════════════════ pricing ═════════════════════════════════ */

const PLANS = [
  {
    name: "Free",
    price: "$0",
    period: "/mo",
    blurb: "For evaluating on a single repo.",
    features: ["100k graph nodes", "5 repositories", "1 MCP client", "Community support"],
    cta: "Get started",
    popular: false,
    onClick: scrollToForm,
  },
  {
    name: "Pro",
    price: "$49",
    period: "/mo",
    blurb: "For teams shipping every day.",
    features: ["1M graph nodes", "Unlimited repositories", "Priority webhook lanes", "SSO & audit log", "Email support"],
    cta: "Get started",
    popular: true,
    onClick: scrollToForm,
  },
  {
    name: "Enterprise",
    price: "Custom",
    period: "",
    blurb: "For orgs with compliance needs.",
    features: ["Dedicated graph cells", "On-prem deployment", "99.9% SLA", "White-glove onboarding"],
    cta: "Contact sales",
    popular: false,
    onClick: () => {
      window.location.href = "mailto:hello@graphsight.dev";
    },
  },
];

function Pricing() {
  return (
    <section className="mx-auto max-w-6xl px-5 py-20">
      <SectionHead eyebrow="Pricing" title="Start free. Scale when your graph does." />
      <div className="mt-14 grid grid-cols-1 items-start gap-5 md:grid-cols-3">
        {PLANS.map((p, i) => (
          <Reveal key={p.name} delay={i * 0.07}>
            <div
              className={cn(
                CARD,
                "relative flex flex-col p-6",
                p.popular && "shadow-[5px_6px_0_0_#059669] md:-mt-4"
              )}
            >
              {p.popular && (
                <span
                  className="absolute -top-3.5 right-5 rounded-full border border-[#131316] px-3 py-1 text-[11px] font-bold text-[#131316]"
                  style={{ backgroundColor: LIME }}
                >
                  Most popular
                </span>
              )}
              <p className="text-sm font-bold text-zinc-600">{p.name}</p>
              <p className="mt-2 text-4xl font-bold tracking-tight text-[#131316]">
                {p.price}
                <span className="ml-1 text-base font-medium text-zinc-500">{p.period}</span>
              </p>
              <p className="mt-2 text-[13.5px] text-zinc-600">{p.blurb}</p>
              <ul className="mt-5 flex-1 space-y-2.5 border-t border-zinc-200 pt-5">
                {p.features.map((f) => (
                  <li key={f} className="flex items-center gap-2.5 text-[13.5px] font-medium text-zinc-700">
                    <Check className="h-4 w-4 shrink-0 text-emerald-600" strokeWidth={2.5} />
                    {f}
                  </li>
                ))}
              </ul>
              <button
                type="button"
                onClick={p.onClick}
                className={cn(
                  "mt-6 w-full rounded-lg py-2.5 text-sm font-bold transition-colors duration-150",
                  p.popular
                    ? cn(BTN_PRIMARY, "shadow-[3px_4px_0_0_#C8F169]")
                    : "border border-[#131316] bg-white text-[#131316] hover:bg-zinc-50"
                )}
              >
                {p.cta}
              </button>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  );
}

/* ═══════════════════════ final CTA ═══════════════════════════════ */

function FinalCta() {
  return (
    <section className="border-t border-zinc-200 bg-[#FAFAFB]">
      <div className="mx-auto max-w-2xl px-5 py-20 text-center">
        <Reveal>
          <span className="mx-auto flex h-11 w-11 items-center justify-center rounded-xl bg-[#131316] shadow-[2px_3px_0_0_#C8F169]">
            <Terminal className="h-5 w-5 text-white" strokeWidth={2} />
          </span>
          <h2 className="mt-5 font-display text-3xl font-bold tracking-[-0.02em] text-[#131316] sm:text-4xl">
            Ready to give your agents a memory?
          </h2>
          <p className="mx-auto mt-3 max-w-md text-[15px] leading-relaxed text-zinc-600">
            Join the waitlist and be first in line when enterprise access opens.
          </p>
        </Reveal>
        <Reveal delay={0.08} className="mt-8 flex justify-center">
          <WaitlistForm inputId="email-cta" center />
        </Reveal>
      </div>
    </section>
  );
}

/* ══════════ install — the pip packages, available today ══════════ */

const PACKAGES = [
  {
    name: "graphsight",
    desc: "The viewer. Opens any trace as an interactive graph in your browser — zero dependencies, nothing leaves your machine.",
    href: "https://pypi.org/project/graphsight/",
  },
  {
    name: "graphsight-langgraph",
    desc: "The tracer. One callback handler records every retriever call, score, and relational path in a LangGraph agent.",
    href: "https://pypi.org/project/graphsight-langgraph/",
  },
];

function Install() {
  return (
    <section className="border-t border-zinc-200 bg-white">
      <div className="mx-auto max-w-6xl px-5 py-20 sm:py-24">
        <SectionHead
          eyebrow="Open source · available today"
          title="See your agent's memory in three commands"
          sub="The hosted graph engine is coming — but the tracer and the viewer ship now, as two small pip packages. Trace any repo or any LangGraph agent, locally."
        />

        <div className="mt-12 grid items-start gap-6 lg:grid-cols-[1.2fr_1fr]">
          {/* terminal walkthrough */}
          <Reveal>
            <div className="rounded-xl border border-[#131316] bg-[#131316] p-4 shadow-[4px_5px_0_0_#C8F169] sm:p-5">
              <div className="mb-4 flex items-center gap-1.5" aria-hidden="true">
                <span className="h-2.5 w-2.5 rounded-full bg-red-400" />
                <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
                <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
              </div>
              <div className="flex flex-col gap-3">
                <p className="font-mono text-[11px] font-bold uppercase tracking-[0.2em] text-zinc-500">
                  1 · install
                </p>
                <CopyCommand command='pip install graphsight "graphsight-langgraph[example]"' />
                <p className="mt-1 font-mono text-[11px] font-bold uppercase tracking-[0.2em] text-zinc-500">
                  2 · trace your repo
                </p>
                <CopyCommand command='graphsight-github-trace your-org/your-repo "who touched auth recently?"' />
                <p className="mt-1 font-mono text-[11px] font-bold uppercase tracking-[0.2em] text-zinc-500">
                  3 · open the graph
                </p>
                <CopyCommand command="graphsight graphsight_out/trace_state.json" />
              </div>
              <p className="mt-4 text-[12.5px] leading-relaxed text-zinc-400">
                Public repos need no token. Your browser opens on the PRs that matched, who
                authored them, and the issues they resolve — every node inspectable.
              </p>
            </div>
          </Reveal>

          {/* package cards */}
          <div className="flex flex-col gap-4">
            {PACKAGES.map((pkg, i) => (
              <Reveal key={pkg.name} delay={0.06 * (i + 1)}>
                <a
                  href={pkg.href}
                  target="_blank"
                  rel="noreferrer"
                  className={cn(
                    CARD,
                    "block p-5 transition-transform duration-150 hover:-translate-y-0.5"
                  )}
                >
                  <p className="flex items-center justify-between font-mono text-[14px] font-bold text-[#131316]">
                    {pkg.name}
                    <span
                      className="rounded-full px-2 py-0.5 text-[10.5px] font-bold"
                      style={{ backgroundColor: LIME }}
                    >
                      PyPI
                    </span>
                  </p>
                  <p className="mt-2 text-[13.5px] leading-relaxed text-zinc-600">{pkg.desc}</p>
                </a>
              </Reveal>
            ))}
            <Reveal delay={0.2}>
              <a
                href="https://github.com/Kcodess2807/graphsight"
                target="_blank"
                rel="noreferrer"
                className="flex items-center justify-center gap-2 rounded-lg border border-[#131316] bg-white px-4 py-3 text-sm font-semibold text-[#131316] shadow-[2px_3px_0_0_#131316] transition-transform duration-150 hover:-translate-y-0.5"
              >
                <Github className="h-4 w-4" strokeWidth={2.25} />
                Star it on GitHub
              </a>
            </Reveal>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ═══════════════════════ page ════════════════════════════════════ */

export function LandingPage() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    document.title = `${BRAND} — Graph memory for AI coding agents`;
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const goToForm = useCallback(scrollToForm, []);

  return (
    <div className="min-h-dvh overflow-x-hidden bg-white font-sans text-zinc-700 antialiased [letter-spacing:-0.011em]">
      {/* ── nav ────────────────────────────────────────────────── */}
      <nav
        className={cn(
          "fixed inset-x-0 top-0 z-50 h-16 border-b transition-colors duration-200",
          scrolled ? "border-zinc-200 bg-white/85 backdrop-blur-xl" : "border-transparent"
        )}
      >
        <div className="mx-auto flex h-full max-w-6xl items-center justify-between px-5">
          <span className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#131316]">
              <Terminal className="h-3.5 w-3.5 text-white" strokeWidth={2} />
            </span>
            <span className="text-[16px] font-bold tracking-tight text-[#131316]">{BRAND}</span>
          </span>
          <div className="flex items-center gap-2">
            <Link
              to="/memory/preview"
              className="rounded-lg px-3 py-1.5 text-sm font-semibold text-zinc-600 transition-colors duration-150 hover:bg-zinc-100 hover:text-[#131316]"
            >
              Live demo
            </Link>
            <a
              href="https://pypi.org/project/graphsight/"
              target="_blank"
              rel="noreferrer"
              className="hidden rounded-lg px-3 py-1.5 text-sm font-semibold text-zinc-600 transition-colors duration-150 hover:bg-zinc-100 hover:text-[#131316] sm:block"
            >
              PyPI
            </a>
            <button
              type="button"
              onClick={goToForm}
              className={cn(BTN_PRIMARY, "px-4 py-2 text-sm shadow-[2px_3px_0_0_#C8F169]")}
            >
              Get started
            </button>
          </div>
        </div>
      </nav>

      <main>
        <Hero />
        <Marquee />
        <CodeShowcase />
        <Install />
        <Stats />
        <UseCases />
        <Benefits />
        <Pricing />
        <FinalCta />
      </main>

      {/* ── footer ─────────────────────────────────────────────── */}
      <footer className="border-t border-zinc-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-5 py-7 sm:flex-row">
          <span className="flex items-center gap-2">
            <span className="flex h-5 w-5 items-center justify-center rounded bg-[#131316]">
              <Terminal className="h-2.5 w-2.5 text-white" strokeWidth={2} />
            </span>
            <span className="text-sm font-bold text-[#131316]">{BRAND}</span>
            <span className="text-xs text-zinc-500">© 2026</span>
          </span>
          <p className="flex items-center gap-4 text-[13px] font-medium text-zinc-500">
            <Link to="/memory/preview" className="transition-colors duration-150 hover:text-[#131316]">
              Live demo
            </Link>
            <a
              href="https://pypi.org/project/graphsight/"
              target="_blank"
              rel="noreferrer"
              className="transition-colors duration-150 hover:text-[#131316]"
            >
              PyPI
            </a>
            <a
              href="https://github.com/Kcodess2807/graphsight"
              target="_blank"
              rel="noreferrer"
              className="transition-colors duration-150 hover:text-[#131316]"
            >
              GitHub
            </a>
            <a href="mailto:hello@graphsight.dev" className="transition-colors duration-150 hover:text-[#131316]">
              Contact
            </a>
            <a href="#" className="transition-colors duration-150 hover:text-[#131316]">
              Privacy
            </a>
          </p>
        </div>
      </footer>
    </div>
  );
}
