import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  ScanSearch,
  Spline,
  Sparkles,
  ShieldCheck,
  AlertTriangle,
  Ticket,
  GitPullRequest,
  User,
  HelpCircle,
  type LucideIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Wordmark } from "@/components/Wordmark";
import { TraceRAGArchitectureFlow } from "@/components/docs/TraceRAGArchitectureFlow";
import { cn } from "@/lib/utils";

const fadeUp = {
  hidden: { opacity: 0, y: 14 },
  show: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.06, duration: 0.5, ease: [0.16, 1, 0.3, 1] },
  }),
};

function Section({
  children,
  index = 0,
  className,
}: {
  children: React.ReactNode;
  index?: number;
  className?: string;
}) {
  return (
    <motion.section
      variants={fadeUp}
      custom={index}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, margin: "-80px" }}
      className={className}
    >
      {children}
    </motion.section>
  );
}

/* -------------------------------------------------------------------------- */
/*  Section 4 — Worked example                                                 */
/* -------------------------------------------------------------------------- */

function ChainStep({
  icon: Icon,
  label,
  accent,
}: {
  icon: LucideIcon;
  label: string;
  accent: string;
}) {
  return (
    <div className="flex shrink-0 items-center gap-2 rounded-lg border border-border bg-white px-3 py-2 shadow-soft">
      <Icon className={cn("h-4 w-4", accent)} />
      <span className="whitespace-nowrap text-xs font-semibold text-zinc-800">
        {label}
      </span>
    </div>
  );
}

function WorkedExample() {
  return (
    <Card className="not-prose overflow-hidden p-0">
      {/* Question */}
      <div className="flex items-center gap-3 border-b border-border bg-zinc-50/70 px-6 py-4">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white text-zinc-500 shadow-soft ring-1 ring-border">
          <HelpCircle className="h-4.5 w-4.5" />
        </span>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
            The question
          </p>
          <p className="font-medium text-zinc-900">
            “Which change broke the payment system?”
          </p>
        </div>
      </div>

      <div className="space-y-6 p-6">
        {/* Skimmer */}
        <div className="flex gap-3">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600 ring-1 ring-indigo-100">
            <ScanSearch className="h-4 w-4" />
          </span>
          <div>
            <p className="text-sm font-semibold text-zinc-900">
              The Skimmer narrows it down
            </p>
            <p className="mt-0.5 text-sm leading-relaxed text-zinc-600">
              Vector Search scans the corpus and surfaces the single most
              relevant artifact — the{" "}
              <span className="font-medium text-indigo-700">
                Payment Error Log
              </span>{" "}
              — out of millions of lines.
            </p>
          </div>
        </div>

        {/* String Board chain */}
        <div className="flex gap-3">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-cyan-50 text-cyan-600 ring-1 ring-cyan-100">
            <Spline className="h-4 w-4" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-zinc-900">
              The String Board follows the trail
            </p>
            <p className="mt-0.5 text-sm leading-relaxed text-zinc-600">
              Graph Traversal then walks the hard links from that log to the
              root cause:
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <ChainStep
                icon={AlertTriangle}
                label="Error Log"
                accent="text-rose-500"
              />
              <ArrowRight className="h-4 w-4 shrink-0 text-zinc-300" />
              <ChainStep icon={Ticket} label="Jira Ticket" accent="text-sky-500" />
              <ArrowRight className="h-4 w-4 shrink-0 text-zinc-300" />
              <ChainStep
                icon={GitPullRequest}
                label="PR #402"
                accent="text-indigo-500"
              />
              <ArrowRight className="h-4 w-4 shrink-0 text-zinc-300" />
              <ChainStep icon={User} label="Priya (Dev)" accent="text-amber-500" />
            </div>
          </div>
        </div>

        {/* Answer */}
        <div className="flex items-center gap-3 rounded-xl border border-emerald-100 bg-emerald-50/60 p-4 ring-4 ring-emerald-500/5">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white text-emerald-600 shadow-soft ring-1 ring-emerald-100">
            <ShieldCheck className="h-5 w-5" />
          </span>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-emerald-700">
              The answer — with its receipts
            </p>
            <p className="font-semibold text-zinc-900">
              Priya’s <span className="font-mono">PR #402</span> caused the
              failure.
            </p>
          </div>
        </div>
      </div>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/*  Reusable explanatory concept card (Section 3 intro)                        */
/* -------------------------------------------------------------------------- */

interface ConceptCardProps {
  icon: LucideIcon;
  eyebrow: string;
  title: string;
  accent: "indigo" | "cyan";
  children: React.ReactNode;
}

function ConceptCard({
  icon: Icon,
  eyebrow,
  title,
  accent,
  children,
}: ConceptCardProps) {
  const styles = {
    indigo: {
      card: "bg-indigo-50/60 border-indigo-100 ring-indigo-500/10",
      chip: "bg-white text-indigo-600 ring-1 ring-indigo-100",
      eyebrow: "text-indigo-600",
      glow: "bg-indigo-200/40",
    },
    cyan: {
      card: "bg-cyan-50/60 border-cyan-100 ring-cyan-500/10",
      chip: "bg-white text-cyan-600 ring-1 ring-cyan-100",
      eyebrow: "text-cyan-600",
      glow: "bg-cyan-200/40",
    },
  }[accent];

  return (
    <Card
      className={cn(
        "relative overflow-hidden p-6 ring-4 transition-shadow hover:shadow-lifted",
        styles.card
      )}
    >
      <div
        aria-hidden
        className={cn(
          "pointer-events-none absolute -right-10 -top-10 h-32 w-32 rounded-full blur-2xl",
          styles.glow
        )}
      />
      <div className="relative">
        <div className="mb-4 flex items-center gap-3">
          <span
            className={cn(
              "flex h-11 w-11 items-center justify-center rounded-xl shadow-soft",
              styles.chip
            )}
          >
            <Icon className="h-5 w-5" />
          </span>
          <div>
            <p
              className={cn(
                "text-[11px] font-semibold uppercase tracking-wider",
                styles.eyebrow
              )}
            >
              {eyebrow}
            </p>
            <h3 className="text-lg font-semibold tracking-tight text-zinc-900">
              {title}
            </h3>
          </div>
        </div>
        <div className="space-y-3 text-sm leading-relaxed text-zinc-600">
          {children}
        </div>
      </div>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/*  Page                                                                       */
/* -------------------------------------------------------------------------- */

export default function TraceRAGConceptsDoc() {
  return (
    <div className="min-h-[100dvh] bg-zinc-50">
      {/* Top bar */}
      <header className="sticky top-0 z-30 border-b border-border bg-white/70 backdrop-blur">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-6 py-3">
          <Button
            asChild
            variant="ghost"
            size="sm"
            className="text-zinc-500 hover:text-zinc-900"
          >
            <Link to="/">
              <ArrowLeft className="h-4 w-4" />
              Back to Dashboard
            </Link>
          </Button>
          <Wordmark />
        </div>
      </header>

      {/* Hero */}
      <div className="relative overflow-hidden border-b border-border">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-gradient-to-b from-indigo-50/70 via-white to-zinc-50"
        />
        <div
          aria-hidden
          className="dotted-grid pointer-events-none absolute inset-0 opacity-[0.5] [mask-image:radial-gradient(ellipse_at_top,black,transparent_70%)]"
        />
        <div className="relative mx-auto max-w-4xl px-6 py-16 sm:py-20">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          >
            <Badge variant="indigo" className="mb-5 gap-1.5">
              <Sparkles className="h-3 w-3" />
              Concepts · How it works
            </Badge>
            <h1 className="text-balance text-4xl font-extrabold tracking-tight sm:text-5xl">
              <span className="bg-gradient-to-r from-indigo-600 via-violet-600 to-cyan-500 bg-clip-text text-transparent">
                Understanding TraceRAG
              </span>
            </h1>
            <p className="mt-5 max-w-2xl text-pretty text-lg leading-relaxed text-zinc-500">
              Why this tool exists, and how it turns an AI that{" "}
              <em className="font-medium not-italic text-zinc-700">guesses</em>{" "}
              into one that{" "}
              <em className="font-medium not-italic text-zinc-700">
                shows its work
              </em>
              — in plain language, no engineering background required.
            </p>
          </motion.div>
        </div>
      </div>

      {/* Body */}
      <main className="mx-auto max-w-4xl px-6 py-14">
        <article className="prose prose-zinc max-w-none prose-headings:scroll-mt-24 prose-headings:font-semibold prose-headings:tracking-tight prose-h2:mb-3 prose-h2:text-2xl prose-p:leading-relaxed prose-p:text-zinc-600 prose-strong:text-zinc-900 prose-em:text-zinc-700">
          <Section index={0}>
            <h2>The Problem: AI That Guesses</h2>
            <p>
              Most AI assistants — including tools like ChatGPT — are, underneath,
              extraordinarily sophisticated guessing machines. They predict the
              next most likely word based on patterns absorbed from across the
              internet. For everyday questions, this works beautifully.
            </p>
            <p>
              But ask a hard, specific question about <em>your own systems</em> —{" "}
              <em>“Which change broke the payment system last Tuesday?”</em> — and
              the cracks appear. The AI has never actually <em>seen</em> your
              incident history. It can’t follow the real chain of events. So it
              does what it always does: it produces a confident, fluent,
              plausible-sounding answer… that may be entirely invented. The
              industry calls this a <strong>“hallucination,”</strong> and in an
              engineering or business setting, a confident wrong answer is worse
              than no answer at all.
            </p>
            <p>
              The issue isn’t that the AI lacks intelligence. It’s that it has no
              way to <strong>see the connections</strong> between your documents,
              tickets, code, and people.
            </p>
          </Section>

          <Separator />

          <Section index={1}>
            <h2>The Solution: An AI That Shows Its Work</h2>
            <p>
              TraceRAG changes the rules. Instead of letting the AI guess, it
              makes the AI behave like a <strong>meticulous investigator</strong>.
            </p>
            <p>
              A good investigator doesn’t walk into a room and announce a theory.
              They gather evidence, follow the trail from one fact to the next,
              and can lay out exactly how they reached their conclusion. If you
              doubt them, they can point to every single step.
            </p>
            <p>
              TraceRAG holds the AI to that same standard. Before it answers, it
              must gather real evidence from your own data, connect the dots, and
              then <strong>show you the trail</strong>. You are never asked to
              simply trust the answer — you can see precisely how it was reached.
            </p>
          </Section>

          <Separator />

          <Section index={2}>
            <h2>The Two Brains</h2>
            <p>
              TraceRAG combines two complementary ways of “thinking,” working
              together like two specialists on the same case — the Skimmer and the
              String Board.
            </p>
          </Section>
        </article>

        {/* Explanatory cards */}
        <Section index={3} className="mt-6 grid gap-5 md:grid-cols-2">
          <ConceptCard
            icon={ScanSearch}
            eyebrow="Vector Search"
            title="🔍 The Skimmer"
            accent="indigo"
          >
            <p>
              Reads fast, and reads everything — racing through thousands of logs
              and documents to surface whatever <em>feels</em> relevant, even when
              the wording differs. Brilliant at <em>meaning</em>, but on its own it
              only finds material that <em>seems</em> related.
            </p>
          </ConceptCard>

          <ConceptCard
            icon={Spline}
            eyebrow="Graph Traversal"
            title="🧵 The String Board"
            accent="cyan"
          >
            <p>
              Like a detective’s cork board strung together with red thread, it
              follows the <em>hard, factual connections</em> — Error Log to Jira
              Ticket to Pull Request to the developer who shipped it — until it
              reaches a precise, defensible answer.
            </p>
          </ConceptCard>
        </Section>

        {/* Animated architecture walkthrough */}
        <Section index={4} className="mt-12">
          <div className="prose prose-zinc mb-7 max-w-none prose-h2:mb-3 prose-h2:text-2xl prose-p:text-zinc-600">
            <h2>The Lifecycle of a Query</h2>
            <p>
              Here is the whole system, end to end. Step through it to watch a
              question travel from the router, split across the two brains, fuse
              back together, and become a fully-traced answer.
            </p>
          </div>
          <TraceRAGArchitectureFlow />
        </Section>

        <Separator />

        {/* Section 4 — Worked example */}
        <Section index={5}>
          <div className="prose prose-zinc mb-6 max-w-none prose-h2:mb-3 prose-h2:text-2xl prose-p:text-zinc-600">
            <h2>TraceRAG in Action</h2>
            <p>
              Here’s the whole machine working end to end on a single, real
              question — the Skimmer to find the starting point, the String Board
              to walk to the culprit.
            </p>
          </div>
          <WorkedExample />
        </Section>

        {/* Closing */}
        <Section index={6} className="mt-12">
          <Card className="flex items-start gap-4 border-emerald-100 bg-emerald-50/50 p-6 ring-4 ring-emerald-500/5">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-white text-emerald-600 shadow-soft ring-1 ring-emerald-100">
              <ShieldCheck className="h-5 w-5" />
            </span>
            <div>
              <h3 className="text-base font-semibold text-zinc-900">
                No black box. Nothing taken on faith.
              </h3>
              <p className="mt-1 text-sm leading-relaxed text-zinc-600">
                Every answer arrives with its receipts — a transparent, verifiable
                trail from question to conclusion. The result is an AI you can
                actually trust in production, grounded in your real connections
                rather than a confident guess.
              </p>
            </div>
          </Card>

          <div className="mt-10 flex justify-center">
            <Button asChild size="lg">
              <Link to="/">
                <ArrowLeft className="h-4 w-4" />
                Back to the Studio
              </Link>
            </Button>
          </div>
        </Section>
      </main>
    </div>
  );
}

/** Local separator with breathing room. */
function Separator() {
  return <hr className="my-10 border-border" />;
}
