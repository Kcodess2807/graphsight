# graphsight changelog

## 0.3.0 — 2026-07-26

- Run diff: select two runs in the history view to see what changed in
  retrieval — items only in A / only in B, score deltas, usage changes.
- Server test suite (routes, path-traversal guard, SPA fallback).

## 0.2.0 — 2026-07-25

- History browsing: `graphsight .graphsight/` serves a directory of traces
  as a clickable run list (`/__runs__.json`, `/__run__/<name>`).
- Renders the retrieved-vs-used split from schema 0.2 traces.

## 0.1.x — 2026-07-24

- Initial release: bundled Studio UI + stdlib localhost server;
  `graphsight trace_state.json` opens a trace; `?src=` auto-load;
  drag-and-drop / paste import page.
