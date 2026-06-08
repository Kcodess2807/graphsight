# TraceRAG — Project Intent

> The *why* behind the code. README explains how to run it; this explains what
> it is trying to be and the reasoning behind the decisions that shaped it.

## The problem

When something breaks in a distributed, multi-repo codebase, the hard question
is rarely "what does this service do?" — it's "**what is connected to what, and
who/what touched it?**" A failing checkout service might trace back to an auth
token change in a *different* repo, merged in a PR by a *specific* person.

Standard vector RAG is blind to that. Embeddings find text that is *semantically
similar* to the query, but they cannot follow a chain of relationships
("Service → depends on → Auth → modified by → PR #847 → authored by → David").
The answer often lives in the *topology*, not in any single similar paragraph.

## The thesis

TraceRAG is a **GraphRAG** system: it builds an explicit knowledge graph of
entities (people, services, PRs, tickets, libraries) and their relationships,
then answers questions by **traversing** that graph as well as searching vectors
— fusing both arms by the query's intent.

The deliberate bet that makes this different from the 2024 Microsoft GraphRAG
line of work: **be a deterministic hybrid, not an LLM-built graph.**

- The graph *scaffolding* comes from hard, deterministic sources (GitHub PR
  metadata, Jira CSV rows, authorship, merge links) — not from asking an LLM to
  hallucinate nodes and edges out of prose.
- ML (GLiNER, spaCy fallback) is used only for the *fuzzy* part: extracting
  entity mentions from text and linking them to nodes.
- The LLM's job is the final mile — turning a retrieved subgraph into a
  plain-language answer a non-expert can follow — grounded strictly in the
  retrieved context.

The intended payoff: near-zero structural hallucination, because the edges are
facts (a PR really did merge, a person really did author it), and a visual
canvas that lets a human *see* the blast radius rather than trust a paragraph.

## Architecture at a glance

- **Backend** — Python / FastAPI. The retrieval engine lives in
  `backend/tracerag/` (`router.py` = hybrid retrieval, `db.py` = LadybugDB graph
  + vector store, `extract.py` = entity extraction, `curation.py` = node
  merging). LadybugDB is a single-file Kùzu-compatible store holding both the
  graph and the HNSW vector index.
- **Frontend** — Vite + React + ReactFlow + Clerk + Tailwind/shadcn. The real
  workhorse is `src/lib/api.ts` (`adaptToTraceState`), which merges the trace
  log + subgraph into the single state the canvas renders.
- **History** — Neon Postgres via SQLModel (users / chat sessions / trace logs),
  so sessions persist and re-hydrate the canvas without re-running the LLM.

## Key design decisions & rationale

**Intent-weighted fusion.** A query is classified relational vs. semantic, and
the vector/graph scores are blended with different weights accordingly
(`ROUTER_WEIGHTS_RELATIONAL` 0.15/0.85 vs `ROUTER_WEIGHTS_CONCEPTUAL` 0.80/0.20).
"Who owns X?" should lean on the graph; "explain the architecture" should lean
on vectors.

**Two-tier intent classification (latency-driven).** Cheap keyword markers
decide intent for free; only genuinely ambiguous queries fall through to a fast
LLM call (Groq `llama-3.1-8b-instant`), with a short timeout and a safe default
to semantic. Intent must never dominate query latency.

**Multiplicative BFS for graph scoring.** A path's score is the *product* of its
edge confidences, so longer/weaker chains naturally decay. Implemented as a
breadth-first frontier expansion in `_graph_stream`.

**Hub throttling.** Super-nodes (degree above `MAX_DEGREE`) are reached but not
*traversed through*, so one hyper-connected entity can't explode the frontier
into a hairball.

**Batched frontier expansion (no N+1).** `expand_frontier` walks an entire BFS
frontier in **one** query per hop instead of one query per node — the difference
between a graph traversal that is the bottleneck and one that is single-digit
milliseconds.

**Warm at boot.** The embedder and extractor are pre-loaded during FastAPI
startup so the *first* query doesn't pay model-load cost; load is moved to
startup, off the critical path.

**Hot-swap graphs without restart.** The active `.lbug` can be swapped at runtime
while the warm models stay resident, so multiple repos can be compared without a
cold restart.

**Bounded caches.** Answer/summary caches are fixed-capacity LRU
(`cache.py`), not unbounded dicts — a long-running server must not leak memory.

**Auth by verified token, never by client claim.** Clerk session JWTs are
verified networklessly against Clerk's JWKS (`auth.py`); the trusted `sub` claim
is the user id. History endpoints scope strictly to that id and check ownership,
closing IDOR — a client cannot read or write another user's sessions by passing
a different id.

## Deliberately out of scope / honest limitations

- **Single-writer DB.** LadybugDB is single-writer; horizontal scaling needs a
  one-writer / read-replica design. Acceptable for a demo / small team; a known
  pre-deploy task, not a solved one.
- **Confidence & token metrics are partly presentational.** The UI "confidence"
  is *derived* from mean edge confidence with a conservative prior, not a
  calibrated uncertainty estimate; some footer metrics (tokens, peak RAM) are
  placeholders. They are display scaffolding, not ground truth — and should be
  described that way.
- **Sync, CPU-bound embedding.** Per-request embedding holds the GIL, so a single
  worker serializes under concurrent load (it degrades by queuing, not failing).
  Throughput scales with workers, not within one.

## Current state

The retrieval → answer pipeline, multi-repo hot-swap, streaming grounded
answers, persistent history, and the auth + IDOR hardening are built and
working. The retrieval engine — batched traversal and multiplicative-BFS scoring
— is the core, defensible work; everything else is the surface that makes it
usable and safe.
