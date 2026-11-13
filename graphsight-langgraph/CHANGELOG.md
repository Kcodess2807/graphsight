# graphsight-langgraph changelog

## 0.3.3 — 2026-11-14

- Episodic recall: `recall()` finds past successful runs in the history dir, and
  `EpisodeRetriever` puts them in an agent's graph, traced like any retriever.
- `capture(..., outcome="success" | "failure")` labels a run. Unlabelled runs
  are never recalled.
- Traces keep each item's `answerOverlap`, and scores read from `score_total`.
- `to_tracestate()` no longer writes `steps`, `weights` or `confidence`. The viewer
  never rendered them, and `confidence` was derived, not measured. Spans are still
  recorded in `AgentTrace`.

## 0.3.2 — 2026-11-07

- `to_tracestate()` carries the final `answer`, so the viewer can show it.

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
