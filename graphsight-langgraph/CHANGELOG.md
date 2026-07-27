# graphsight-langgraph changelog

## 0.3.0 — 2026-07-26

- `finish()` now defaults the answer to the last LLM generation the tracer
  saw — `capture(tracer)` alone is a complete integration for LLM agents.
- Async verified: `ainvoke` runs covered by the test suite.
- Test suite added (tracer sync+async, mapper contract, capture).
- Shared tokenizer internals (`_text.py`); behavior unchanged.

## 0.2.0 — 2026-07-25

- Retrieved-vs-used: per-item `answer_overlap` (lexical, labeled heuristic);
  unused retrievals render dimmed in the viewer. Schema 0.2 (additive).
- Run history: `capture()` / `save_trace()` write timestamped traces to
  `./.graphsight/` (or `$GRAPHSIGHT_DIR`).
- `graphsight-github-trace` ingests commits (`--commits`), so repos with no
  PRs/issues still produce a full graph; readable commit labels; zero-score
  items no longer claim a score.

## 0.1.x — 2026-07-24

- Initial release: `LangGraphTracer` callback handler, `AgentTrace` v0.1
  schema, `to_tracestate()` mapper, GitHub ingest CLI, offline demo.
