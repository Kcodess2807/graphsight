# Graphsight — Meeting Kit

Private crib sheet for senior-dev / VC conversations. Not marketing copy —
memorize the shape, speak it naturally.

---

## The 30-second pitch

> When an AI agent answers from retrieved context, nobody can see *why it
> picked what it picked*. When the answer is wrong, you're debugging blind.
>
> Graphsight is the lens: one callback handler records every retriever
> call — scores, relational paths, and what the answer actually used — and
> renders it as an interactive graph in your browser. Two pip packages,
> zero dependencies, nothing leaves your machine.
>
> Live on PyPI today. The wedge is retrieval debugging for LangGraph
> agents; the arc is the observability tier for agent memory.

One-liners to have loaded:

- **vs storage (HelixDB, Neo4j):** "Helix stores the memory. Graphsight
  explains it. They sell before your agent runs; I sell after it fails."
- **vs LangSmith/Langfuse:** "They show you a table of spans. I show you
  the *shape* of the retrieval — who authored what, which fix resolves
  which incident. Graph-native is the part table-first UIs can't retrofit."
- **the honesty angle:** "The viewer never paraphrases evidence with an
  LLM. Every node is click-through-verifiable at its source. If a score
  wasn't computed, we don't render one."

## The 3-minute live demo (rehearsed, works offline, no API keys)

From `graphsight-langgraph/` with any Python ≥3.10:

```bash
pip install graphsight "graphsight-langgraph[example]"   # if fresh machine

python example/failure_demo.py     # 1. agent answers WRONG, console says why
graphsight .graphsight/            # 2. run history opens in browser
```

Narration beats, in order:

1. **The failure** — "I asked why checkout payments fail since yesterday's
   deploy. The agent confidently blames an 8-month-old PR and suggests
   re-applying it. Classic RAG failure — and normally you'd never know why."
2. **Open the run** (click it in history) — "Here's every candidate it
   retrieved. The stale PR scored 0.91 — it *talks* like the question.
   The actual cause, yesterday's SDK bump, scored 0.34 — a deps-only diff
   shares no words with 'checkout failing'."
3. **The graph path** — "But look at the edges: the sev-1 incident reports
   on payment-service, and the SDK bump touches payment-service. The
   relational path finds what similarity can't. Similarity ≠ causality."
4. **Retrieved vs used** — "And the dimmed nodes? Retrieved but *ignored*
   by the answer. The two classic failures — right doc ignored, wrong doc
   trusted — visible at a glance."
5. **Close** — "Every node click-through-verifiable. No LLM anywhere in
   this pipeline. `pip install graphsight` and this runs on your agent
   today with one callback handler."

Optional flex if they name a public GitHub repo:
`graphsight-github-trace their-org/their-repo "who touched auth recently?"`
then open the trace. (Needs network; falls back gracefully on rate limits.)

## Numbers to have memorized

- 2 packages on PyPI: `graphsight` (viewer, **zero** runtime deps, stdlib
  server) and `graphsight-langgraph` (adapter, one dep: `langchain-core`).
  Both at 0.2.0; 13 releases shipped across ~2 weeks.
- Integration cost: **one callback handler** — no code changes to the graph.
- Verified against langchain-core 1.5.0 + current LangGraph.
- The full engine behind it: hybrid vector+graph store in a single embedded
  file, two-tier entity resolution, intent-weighted routing, MCP server,
  multi-tenant pipeline — e2e-tested, in the same repo.
- Team of 3 (me: backend + AI logic; Vishal: backend; Utsav: frontend + AI).

## Hard questions — honest answers

**"Isn't this a feature of LangSmith, not a company?"**
Today, yes — it's a wedge, deliberately. The expansion path is: history →
run diffing → always-on capture → team trace sharing → the graph memory
tier itself. And graph-native rendering is genuinely hard to retrofit onto
table-first tools; it's their architecture debt, my starting point.

**"What's the moat?"**
Early: taste + speed + the neutral schema. `AgentTrace` is framework-neutral
by design — LangGraph today, LlamaIndex next, HelixDB and raw OTel after.
Storage vendors are structurally biased toward their own engine; a neutral
lens across all of them is a position no incumbent can occupy. Long-term
moat is accumulated trace history — once your debugging record lives here,
switching costs are real.

**"Market size?"**
Agent observability is where APM was in 2012 — LangSmith and Langfuse are
proving spend exists. I'm not sizing the whole category; I'm after the
slice where retrieval is relational (multi-hop, entity-linked, graph
memory) — small today, but it's the direction agent memory is moving, and
HelixDB raising on exactly that thesis is my favorite third-party evidence.

**"Traction?"**
Pre-traction, honestly: packages went live this week, friends-beta is
starting now. What I have is velocity — idea to two published, verified
packages in under two weeks — and a tight feedback loop with named beta
questions ("did the graph tell you anything the answer didn't?").

**"Why did you kill the original SaaS?"**
A 15-year industry reviewer called it infra theater — he was right. The
integrated database + multi-tenant pipeline was solving my problem, not a
user's. I stripped it to the part with a real moment of need: the trace.
The engine still exists and works; it re-enters as the hosted tier only if
the wedge earns it.

**"What breaks this?"**
Two things, and I watch both: (1) if retrieval debugging turns out to be a
rare moment, this is a vitamin — beta feedback answers that within weeks;
(2) if agent retrieval stays vector-only forever, the graph view loses its
edge — that's why v0.2 added retrieved-vs-used, which is valuable on
*flat* vector RAG too. I'd rather name the risks than have you find them.

**"Your benchmark said token reduction was ~0%."**
Yes — §VIII reports it plainly: the thesis didn't hold on that dataset and
the section explains why. That honesty is the product's brand. The pivot to
observability exists partly *because* I benchmark my own claims.

**"Business model?"**
Open-source packages as top of funnel. Paid: hosted trace history +
team collaboration (share, diff, annotate), then the managed memory tier
over MCP. Individuals free forever — the local tool costs me nothing.

## The ask

Tune to the room, but the honest version:

- **Senior devs:** "Wire it into one real agent you run, and tell me if the
  trace ever tells you something the logs didn't. If it never does, I want
  to know that even more."
- **VCs:** "Too early for a round and I know it. What I want: intros to
  2–3 teams running LangGraph in production for the beta, and a
  30-minute follow-up when I have retention data from it."

## Links

- PyPI: pypi.org/project/graphsight · pypi.org/project/graphsight-langgraph
- Repo: github.com/Kcodess2807/graphsight
- Beta script: BETA.md at repo root
