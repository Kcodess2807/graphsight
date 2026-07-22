# graphsight-langgraph

[![PyPI](https://img.shields.io/pypi/v/graphsight-langgraph.svg)](https://pypi.org/project/graphsight-langgraph/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://pypi.org/project/graphsight-langgraph/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](https://github.com/Kcodess2807/graphsight/blob/main/graphsight-langgraph/LICENSE)

**See exactly why your LangGraph agent picked the context it picked.**

Retrieval in an agent is a black box: documents go in, an answer comes out,
and when the answer is wrong you're left guessing which context misled it.
This package opens the box. One callback handler records a
[LangGraph](https://github.com/langchain-ai/langgraph) run — every node,
every retriever call, per-document scores, and (for graph-aware retrievers)
the relational paths between retrieved entities — and one command renders it
as an interactive graph in your browser.

```
your LangGraph agent ──▶ LangGraphTracer ──▶ AgentTrace (v0.1) ──▶ graphsight viewer
                          (callbacks)         neutral JSON          interactive graph
```

Only dependency: `langchain-core`. No engine, no backend, no account —
nothing leaves your machine.

## Installation

```bash
pip install graphsight-langgraph            # the tracer
pip install "graphsight-langgraph[example]" # + langgraph, for the GitHub CLI
pip install graphsight                      # the local viewer (recommended)
```

### Compatibility

| | |
|---|---|
| Python | ≥ 3.10 |
| `langchain-core` | ≥ 0.3 (verified against 1.5.0) |
| `langgraph` | any recent version; only needed for the `[example]` extra |
| Sync (`invoke` / `stream`) | verified |
| Async (`ainvoke` / `astream`) | same callback events; not yet covered by the verification run |

## Quickstart: trace a GitHub repo in 60 seconds

No setup, no API keys — public repositories don't need a token:

```bash
graphsight-github-trace langchain-ai/langgraph "who fixed the recent streaming bugs?"
graphsight graphsight_out/trace_state.json
```

Your browser opens on a live graph of that repository's recent activity:
the PRs that matched the question, the people who authored them, the issues
they resolve — every node clickable, scores shown, execution timeline
included.

### `graphsight-github-trace` reference

```
graphsight-github-trace REPO [QUESTION] [options]
```

| Argument | Default | Description |
|---|---|---|
| `REPO` | — | `owner/name`, e.g. `langchain-ai/langgraph`. |
| `QUESTION` | *"What changed recently in \<repo\>, and who drove it?"* | The question the traced retrieval answers. |
| `--token` | `$GITHUB_TOKEN` | GitHub token. Required for private repositories; raises the rate limit on public ones. |
| `--prs` | `25` | Recent pull requests to fetch. |
| `--issues` | `25` | Recent issues to fetch. |
| `--commits` | `25` | Recent commits to fetch — solo repos with no PRs/issues still produce a full graph. |
| `--top` | `10` | Items the retrieval keeps. |
| `--out` | `graphsight_out/` | Output directory for `agent_trace.json` and `trace_state.json`. |

Method note: the CLI builds a corpus with relational edges
(`person AUTHORED pr/commit`, `pr RESOLVES issue`, `pr TOUCHES repo`) and
ranks by **lexical overlap with 1-hop graph expansion** — deliberately
simple, and reported as such. The scores you see are exactly the scores
computed; nothing is presented as semantic similarity.

Ask it *who / what / when* questions ("who touched auth recently?", "which
issue needed two attempts?") — that's what commit and PR history can answer.
*How-does-it-work* questions need semantic retrieval over code and docs,
which this deliberately simple demo does not pretend to do.

## Tracing your own agent

The complete integration:

```python
from graphsight_langgraph import LangGraphTracer, to_tracestate

tracer = LangGraphTracer()
result = graph.invoke(inputs, config={"callbacks": [tracer]})

trace = tracer.finish(query="why is checkout failing?", answer=result["answer"])
to_tracestate(trace)     # viewer-ready dict — json.dump it, then: graphsight trace.json
```

### Configuration propagation (read this once)

LangChain only propagates callbacks into runnables that receive the run's
config. Inside a LangGraph node, pass the node's config through to
sub-runnables, or the tracer will record the node but not what happened
inside it:

```python
def retrieve(state, config):                               # 1. accept config
    docs = retriever.invoke(state["q"], config=config)     # 2. pass it through
    return {"docs": docs}
```

**Symptom if you skip this:** the trace shows node spans but zero
retrievals.

### API reference

| Name | Description |
|---|---|
| `LangGraphTracer()` | `BaseCallbackHandler` subclass. Pass via `config={"callbacks": [tracer]}` to `invoke` / `stream`. Reusable within a single run; create a fresh instance per run. |
| `tracer.finish(query=None, answer=None) -> AgentTrace` | Assembles the trace after the run: closes dangling spans, computes total latency. `query` falls back to the first retriever query seen. |
| `to_tracestate(trace) -> dict` | Maps an `AgentTrace` to the viewer's JSON contract. Serialize with `json.dump`. |
| `trace.to_dict() -> dict` | The framework-neutral `AgentTrace` (schema v0.1) for your own tooling. |
| `AgentTrace`, `Span`, `Retrieval`, `RetrievedItem`, `TraceEdge` | Plain dataclasses defining the schema; importable for custom emitters. |

## What gets captured

| Source in the run | Captured as |
|---|---|
| Each LangGraph node execution | `Span(kind="node")` with monotonic-clock timing |
| Framework internals (`RunnableSequence`, `ChannelWrite`, `__start__`, …) | filtered out — one span per user node |
| `on_retriever_end` documents | one `RetrievedItem` per doc: id, label, kind, score, content, source |
| `Document.metadata` score keys (`score`, `relevance_score`, `similarity`, `_score`, `vector_score`) | item scores |
| `Document.metadata["edges"]` | relational edges, deduplicated per retrieval |
| LLM / tool calls | plain spans in the execution timeline |
| Edges present in a retrieval | `arm = "graph"`, else `"vector"` — detected automatically |

### Making your retriever graph-aware

The tracer reads two optional metadata conventions from the `Document`
objects your retriever returns:

```python
Document(
    page_content="PR #4821 'fix: idempotent refund path' merged by Priya N. ...",
    metadata={
        "id": "pr_4821",             # stable node id (falls back to a content hash)
        "label": "PR #4821",         # display name
        "kind": "pull_request",      # normalized to a viewer entity type, see below
        "score": 0.94,               # any recognized score key
        "source": "https://github.com/acme/platform/pull/4821",
        "edges": [                   # optional — enables the relational view
            {"source": "pr_4821", "target": "svc_checkout",
             "relation": "TOUCHES", "weight": 0.9},
        ],
    },
)
```

`kind` values are normalized (`pull_request → PR`, `service → Service`,
`person`/`author` → `Person`, `ticket`/`issue`/`jira` → `Ticket`,
`repo → Repo`, `library → Library`, `team → Team`, `tool → Tool`; anything
else renders as `Document`).

### Degradation behavior

- **No edges in metadata** → a flat scored-retrieval view instead of
  relational path highlighting. Still useful; not graph-aware.
- **No recognized score keys** → scores stay `None`; no score chips render.
  Nothing is ever fabricated.
- The emitted `confidence.rationale` states that scores came from your
  retriever and were not recomputed — an imported trace never masquerades
  as an engine-computed one.

## Schema (v0.1)

`AgentTrace` is the stable contract. Future adapters (LlamaIndex, raw
OpenTelemetry) emit the same shape and render in the same viewer.

```jsonc
{
  "schema_version": "0.1",
  "framework": "langgraph",
  "query": "…",
  "spans": [
    { "id": "…", "name": "retrieve", "kind": "node",       // node | retriever | llm | tool
      "parent_id": null, "start_ms": 0.0, "end_ms": 0.3, "status": "ok" }
  ],
  "retrievals": [
    {
      "span_id": "…", "query": "…",
      "arm": "graph",                                       // "vector" | "graph", auto-detected
      "items": [
        { "id": "pr_4821", "label": "PR #4821", "kind": "pull_request",
          "score": 0.94, "vector_score": null, "graph_score": null,
          "content": "…", "source_uri": "https://…", "metadata": {} }
      ],
      "edges": [                                            // optional — the relational view
        { "source": "pr_4821", "target": "svc_checkout", "relation": "TOUCHES", "weight": 0.9 }
      ]
    }
  ],
  "answer": "…",
  "latency_ms": 3.9
}
```

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Node spans but no retrievals | Config not propagated into the node's sub-runnables — see [Configuration propagation](#configuration-propagation-read-this-once). |
| Items without scores | Your retriever doesn't write a recognized score key to `Document.metadata` — add one (`score` is simplest). |
| Flat graph, no edges | Your retriever doesn't emit `metadata["edges"]` — see [Making your retriever graph-aware](#making-your-retriever-graph-aware). |
| `GitHub API 403` from the CLI | Rate limit (60 requests/hour unauthenticated) — pass `--token` or set `GITHUB_TOKEN`. |
| Garbled output on Windows consoles | Fixed in ≥ 0.1.1; upgrade. |

## Roadmap

In order: a **LlamaIndex adapter** emitting the same `AgentTrace`, then a
raw **OpenTelemetry span** ingestor. The schema is the contract; adapters
stay thin.

## Links

- Source & issue tracker: [github.com/Kcodess2807/graphsight](https://github.com/Kcodess2807/graphsight)
- The viewer: [graphsight on PyPI](https://pypi.org/project/graphsight/)
- Beta test script: [BETA.md](https://github.com/Kcodess2807/graphsight/blob/main/BETA.md)

## License

MIT © Arush Karnatak
