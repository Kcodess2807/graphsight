# graphsight

[![PyPI](https://img.shields.io/pypi/v/graphsight.svg)](https://pypi.org/project/graphsight/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://pypi.org/project/graphsight/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](https://github.com/Kcodess2807/graphsight/blob/main/graphsight/LICENSE)

**See exactly why your AI agent retrieved what it did.**

Your agent answered a question. Which documents did it actually pull? What
scores did they get? How are they connected to each other? Most stacks make
you dig through logs to answer that. Graphsight renders the run as an
**interactive graph in your browser** — one command, zero dependencies,
nothing leaves your machine.

```bash
pip install graphsight
graphsight path/to/trace_state.json
```

## What you get

- **Every retrieved item as a typed node** — PR, Service, Person, Ticket,
  Document, Repo, Library, Team, Tool — with its retrieval score.
- **Relational paths between results** — *person → authored → PR →
  resolves → issue* — the chain of evidence, not just a ranked list.
- **An inspector on every node**: underlying content, score, source link.
- **The execution timeline** of the run: each agent step, each retriever
  call, per-span timings, and which retrieval arm (vector / graph) produced
  the results.

## Requirements

| | |
|---|---|
| Python | ≥ 3.10 |
| Runtime dependencies | **none** (stdlib only) |
| Platforms | Windows, macOS, Linux |
| Browser | any modern browser |

## Usage

```
graphsight [trace] [--port PORT] [--no-browser]
```

| Argument | Default | Description |
|---|---|---|
| `trace` | — | Path to a `trace_state.json`. Optional — omit to open the import page and drag-and-drop or paste JSON instead. |
| `--port` | `4630` | Local port to serve on. |
| `--no-browser` | off | Start the server without opening a browser window. |

The server binds to `127.0.0.1` only and runs until you press `Ctrl+C`.

## Producing traces

Graphsight renders any file matching its trace JSON contract. Current
producers:

- **[graphsight-langgraph](https://pypi.org/project/graphsight-langgraph/)** —
  instrument any [LangGraph](https://github.com/langchain-ai/langgraph)
  agent with a single callback handler, or trace a GitHub repository in one
  command:

  ```bash
  pip install "graphsight-langgraph[example]"
  graphsight-github-trace langchain-ai/langgraph "who fixed the recent streaming bugs?"
  graphsight graphsight_out/trace_state.json
  ```

- **The TraceRAG engine** — the graph-memory backend this project grew out
  of; its `/api/trace` responses are the same shape.

Adapters for LlamaIndex and raw OpenTelemetry spans are planned; all
producers emit the same schema and render in this same viewer.

### Writing your own producer

The minimum contract is small — a JSON object with:

```jsonc
{
  "query": "the question that was asked",          // required, string
  "graph": {
    "nodes": [{ "id", "label", "type", "score", "meta": { "snippet", "sourceUrl" } }],
    "edges": [{ "id", "source", "target", "relation", "confidence" }]
  },
  "steps":   [ /* execution timeline, optional */ ],
  "metrics": { "queryTimeSec": 0.004 }             // optional
}
```

Node positions are computed client-side; emitters never deal with layout.
The complete schema and a reference emitter live in the
[graphsight-langgraph source](https://github.com/Kcodess2807/graphsight/tree/main/graphsight-langgraph).

## Security and privacy

- The dependency list is empty by design: the UI is a bundled static build
  (Vite + React + React Flow) served by Python's stdlib `http.server`.
- Binds to `127.0.0.1` — not reachable from other machines.
- No accounts, no telemetry, no outbound network calls. Your traces stay on
  your disk.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `Address already in use` | Another process holds the port — pass `--port 4631`. |
| Browser doesn't open | Some environments (SSH, WSL, containers) can't launch one — start with `--no-browser` and open the printed URL yourself. |
| `Bundled UI missing` error | Broken installation — `pip install --force-reinstall graphsight`. |
| Page loads but trace doesn't | The JSON didn't match the contract — the import page shows the specific validation error. |

## Links

- Source & issue tracker: [github.com/Kcodess2807/graphsight](https://github.com/Kcodess2807/graphsight)
- LangGraph adapter: [graphsight-langgraph on PyPI](https://pypi.org/project/graphsight-langgraph/)
- Beta test script: [BETA.md](https://github.com/Kcodess2807/graphsight/blob/main/BETA.md)

## License

MIT © Arush Karnatak
