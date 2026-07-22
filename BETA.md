# Graphsight — Beta for Friends

Thanks for trying this. I want your honest take — including *"this is cool
but I wouldn't use it."*

## What it actually is

**Graphsight captures exactly why your AI agent retrieved what it did.**

It records every retriever call, per-item scores, which retrieval arm
produced each result (vector vs graph), and the relational paths between
results (e.g. **person → PR → Service → Issue**) — then renders it as an
interactive graph in the browser: every node clickable, with the underlying
evidence, score, and source link in an inspector, plus the execution
timeline of the run that produced it.

You get full visibility into the retrieval reasoning instead of a black box.

Two pip packages. No backend, no account, nothing leaves your machine.

## Quick try — instant demo (2 minutes)

```bash
pip install graphsight "graphsight-langgraph[example]"

git clone https://github.com/Kcodess2807/graphsight
cd graphsight/graphsight-langgraph
python example/demo_agent.py          # runs a small LangGraph agent + tracer
graphsight example/out/trace_state.json
```

Browser opens → you'll see 4 entities, the traced retrieval path, scores,
and the execution timeline.

> Not on PyPI yet? From the repo root:
> `pip install ./graphsight "./graphsight-langgraph[example]"`

## Try it on your own repo (5–8 minutes)

```bash
# ingest + trace a query against your GitHub repo
graphsight-github-trace yourusername/yourrepo "who changed authentication recently?"

# open it in the Studio
graphsight graphsight_out/trace_state.json
```

Now the graph is *your* PRs, *your* issues, *your* commits, *your* people —
what matched the question, who authored it, which issues it resolves.

Works on public repos with no token. Private repos need `GITHUB_TOKEN`.
Repos with no PRs or issues still work — recent commits carry the history.

Tip: ask *who / what / when* questions ("who touched auth recently?"), not
*how-does-it-work* questions — commit history describes changes, not
architecture, and the tool won't pretend otherwise.

**If you already build with LangGraph**, wiring the tracer into your own
agent is one callback handler:

```python
tracer = LangGraphTracer()
graph.invoke(inputs, config={"callbacks": [tracer]})
```

— see [graphsight-langgraph/README.md](graphsight-langgraph/README.md).

## What I want your blunt feedback on

1. **Did the graph tell you anything useful that the raw answer didn't?**
   If not, this is decoration and I need to know.
2. **Would you actually wire this tracer into a real agent you run
   regularly?** Why / why not — trust, effort, or no need?
3. **What's missing before this becomes part of your workflow?**
   Comparing two runs? Auto-capture on failure? Better filtering?
   Something else entirely?

Drop feedback as a GitHub issue on this repo, or DM me directly.

## Current limitations (no surprises)

- The GitHub trace uses simple lexical matching + 1-hop graph expansion for
  now — labeled as such in the output, and sometimes dumb.
- Scores come directly from your retriever — nothing is invented. Missing
  scores render as missing.
- Async LangGraph (`ainvoke`/`astream`) support is next; sync is verified.
- The full `/studio` route expects the complete TraceRAG backend — this
  beta focuses on `/memory/import`, which needs nothing.
