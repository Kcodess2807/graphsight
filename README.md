# TraceRAG — The Observable GraphRAG Engine

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![React + Vite](https://img.shields.io/badge/UI-React%20%2B%20Vite-61DAFB.svg)](https://vitejs.dev/)
[![LadybugDB](https://img.shields.io/badge/storage-LadybugDB-red.svg)](https://github.com/ladybugdb/ladybug)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> A local-first, observability-driven GraphRAG pipeline. Vectors **and** graph live in a single
> `.lbug` file — no dual-store sync — behind a two-tier entity-resolution engine, an
> intent-weighted hybrid router, and a visual tracer that lets you *see* why the retriever chose
> what it chose.

---

## I. Overview

Multi-hop retrieval for agents tends to fail for three infrastructural reasons:

1. **Dual-store sync hell** — keeping a graph database and a vector database consistent.
2. **Entity drift** — the *"Janitor Problem"*: unconstrained LLM extraction turns
   `PaymentService`, `payments-v2`, and `pay_svc` into three separate nodes.
3. **Black-box routing** — no insight into why a hybrid retriever weighted a graph edge over a
   semantic chunk.

**TraceRAG** is an orchestration and observability layer (not a new database) that addresses all
three:

- **Zero-sync storage** — semantic vectors (`FLOAT[384]`) and the relational graph live natively
  in one embedded **LadybugDB** file.
- **Two-tier curation** — a cheap vector pass auto-merges obvious duplicates; a local-LLM pass
  (Groq) adjudicates only the ambiguous "grey zone," keeping the graph clean without a human
  janitor.
- **Traceable routing** — every query returns a structured `trace_log` (intent weights, vector
  seeds, graph hops) that **TraceRAG Studio** renders so stakeholders can watch the reasoning path.

On top of the retrieval core sits a secured application layer: streamed, grounded answers with
clickable citations, multi-graph hot-swapping, persistent session history, and end-to-end
authentication and rate limiting.

This document reports what was built **and how it actually performs** — including a candid
benchmark section (§VI) where the headline thesis did *not* hold on the current data, and why.

---

## II. Architecture & Stack

| Layer | Technology | Role |
|---|---|---|
| **Embeddings** | `sentence-transformers` · `all-MiniLM-L6-v2` | 384-dim sentence vectors (cosine) |
| **Entity extraction** | **GLiNER** (designed) / **spaCy** (current fallback) | Zero-shot domain NER; see §VI for why spaCy is active |
| **Storage** | **LadybugDB** (embedded, Kùzu-lineage) | Single-file hybrid vector + graph store with a native HNSW `VECTOR` extension |
| **LLM — extraction / intent** | **Groq** · `llama-3.1-8b-instant` | Grey-zone entity disambiguation + router intent fallback |
| **LLM — generation** | **OpenRouter** · `anthropic/claude-3-haiku` (default) | Grounded plain-language answers + node summaries |
| **API** | **FastAPI** + Uvicorn | Headless backend: trace, subgraph, answer, graphs, history |
| **Auth** | **Clerk** (frontend) + **PyJWT / JWKS** (backend) | Networkless session-token verification; dev-bypass when unconfigured |
| **History** | **Neon Postgres** via **SQLModel** | Users, chat sessions, persisted trace logs |
| **Frontend** | **Vite + React + ReactFlow** · Tailwind / shadcn | TraceRAG Studio — visual query tracer |

### Repository layout

```
backend/
├── api.py                  # FastAPI app: trace, subgraph, answer, graphs, suggestions, health
├── auth.py                 # Clerk JWT verification (PyJWT + JWKS) + dev-bypass dependency
├── cache.py                # bounded OrderedDict LRU for the answer / summary caches
├── ratelimit.py            # per-user slowapi limiter (keyed by the verified user id)
├── database.py             # SQLModel engine / session for the Postgres history store
├── models.py               # User / ChatSession / TraceLog tables
├── routers/
│   └── history.py          # session + trace-log endpoints (ownership-checked)
├── tracerag/
│   ├── config.py           # single source of truth for thresholds, weights, models
│   ├── db.py               # LadybugDB connection, schema, HNSW index, graph queries
│   ├── extract.py          # GLiNER (→ spaCy fallback) + word-based sliding window
│   ├── curation.py         # two-tier resolution (vector fast-merge + Groq grey-zone)
│   ├── router.py           # intent classification + dual-stream rank fusion + trace_log
│   ├── llm.py              # Groq / OpenRouter client factories
│   └── integrations/
│       └── langchain.py    # drop-in BaseRetriever
└── scripts/
    ├── ingest.py           # headless ingest CLI
    ├── ingest_github.py    # multi-repo GitHub PR connector
    ├── benchmark.py        # LLM-as-judge evaluation → results.csv
    ├── stress_test.py      # async load test (graceful-degradation)
    └── ratelimit_test.py   # burst test verifying the per-user rate limit

frontend/
└── src/
    ├── components/         # TraceDashboard + left (query/answer) & right (canvas) panes
    ├── lib/                # api client, auth-token bridge, dagre layout, Clerk helpers
    ├── data/               # mock trace for the offline fallback
    └── types/              # shared TraceState / node / edge types
```

### Data model

A single generic `Entity` node table (`id, label, type, embedding`) keeps the schema dynamic
across all entity labels. `Document` nodes store one **sliding-window chunk** each (with raw
`content` for generation). Edges: `Document -[MENTIONS]-> Entity` and `Entity -[RELATES_TO]->
Entity` (only between entities co-occurring in the *same* window — no document-wide hairball).

---

## III. Entity Resolution — The Two-Tier "Janitor"

Every extracted mention is embedded and compared (cosine) against already-resolved nodes. The
decision is tiered to spend LLM budget only where it matters:

| Similarity | Action | Cost |
|---|---|---|
| **≥ 0.92** | **Fast Mode** — auto-merge into the existing canonical node | 0 LLM calls |
| **0.85 – 0.92** | **Deep Merge** — ask Groq *"Are 'X' and 'Y' the exact same entity? YES/NO"* (`temperature=0`) | 1 Groq call |
| **< 0.85** | Mint a new node (deterministic slug id) | 0 LLM calls |

Canonical nodes are **never** overwritten on merge (a later, noisier surface form can't clobber
the clean label/embedding), and Groq failures **fail-safe to NO** — the engine prefers a duplicate
node over a hallucinated merge.

> **Implementation note.** This LadybugDB build's HNSW index is *static* (the indexed property
> can't be mutated once the index exists), so curation does its dedup search **in-memory**
> (normalized-cosine) during ingest, and the persistent HNSW index is built **once afterward** for
> query-time retrieval.

**Observed on the test corpus (7 docs, 255 raw mentions):**

| Metric | Value |
|---|---|
| Raw extracted mentions | 255 |
| Canonical nodes after curation | **135** |
| Entity consolidation | **≈ 47%** |
| Fast-mode auto-merges (≥0.92) | 117 |
| Groq grey-zone adjudications (0.85–0.92) | 12 (→ 3 merged, 9 kept distinct) |

---

## IV. Intent-Based Hybrid Routing

The router never uses static weights. It classifies query intent, then fuses two retrieval streams:

```
S = α · s_v + β · s_g          (α + β = 1)
```

- `s_v` = vector similarity (`1 − cosine_distance`) from the HNSW index.
- `s_g` = graph **PathScore** — the product of edge confidences along the traversal from the vector
  "seed" nodes (seeds score `1.0`).

**Dynamic weighting:**

| Intent | α (vector) | β (graph) | Trigger |
|---|---|---|---|
| **Semantic / conceptual** | **0.80** | 0.20 | keywords (*explain, architecture, overview…*) |
| **Relational / multi-hop** | 0.15 | **0.85** | keywords (*who, caused by, which PR, depends on…*) |
| *ambiguous* | — | — | Groq fallback classifier (`SEMANTIC` / `RELATIONAL`) |

The graph traversal is a batched, multiplicative-confidence BFS: each hop expands the **entire
frontier in one query** (no N+1), and hub super-nodes above a degree threshold are reached but not
traversed through, so the frontier can't explode into a hairball. Every call emits a `trace_log`
consumed by the UI:

```json
{
  "intent": { "alpha": 0.15, "beta": 0.85, "type": "relational" },
  "execution_path": {
    "vector_seeds": ["paymentservice-service", "..."],
    "graph_hops":  [{ "from_id": "...", "to_id": "...", "confidence": 0.9 }]
  },
  "metrics": { "total_nodes_evaluated": 18 }
}
```

---

## V. Application Layer — TraceRAG Studio

Retrieval is half the loop; the Studio closes it with generation, exploration, and observability
over the retrieved subgraph.

**Visual observability.** The backend is fully decoupled from the UI: `POST /api/trace` returns the
ranked nodes *and* the `trace_log`, and `POST /api/subgraph` returns a bounded neighborhood
(requested nodes + 1-hop neighbors + interconnecting edges) so the browser never renders the whole
graph. The canvas shows which nodes came from the **vector** arm vs the **graph** arm, the exact
**α / β** the router chose, the **hop path** the traversal walked, and a dimmed 1-hop context around
the active trace. When a hybrid retriever makes a surprising choice, you can *see* why.

**Grounded answers (streamed).** `POST /api/answer/stream` produces a concise, plain-language answer
from the **retrieved context only** (OpenRouter), streamed token-by-token and cached per
`(query, context)`. If the context doesn't cover the question, the model is instructed to say so
rather than guess.

**Clickable citations.** Entity mentions in the answer (people, PRs, services) render as chips that
pan, zoom, and highlight the matching node on the canvas — turning a claim into traceable evidence.
Mentions are matched with word-boundary–safe lookarounds, so labels such as `PR #5818` resolve
correctly without false matches inside longer words.

**Graph-aware suggestions.** `GET /api/suggestions` derives example questions from the active graph's
hub entities, so users only ask what the loaded graph can actually answer.

**Multi-graph hot-swap.** `GET /api/graphs` + `POST /api/graphs/switch` change the active `.lbug` at
runtime without a restart — warm models stay resident. The frontend persists the selection across
reloads.

**Session history.** Chat sessions and their `trace_log`s persist to Postgres and re-hydrate the
canvas on demand, with no LLM call on replay.

---

## VI. Security & Operational Hardening

The billed and user-data surface is protected end-to-end:

- **Authentication.** Clerk session JWTs are verified networklessly against Clerk's JWKS (PyJWT,
  RS256) — signature, expiry, issuer, and authorized-party are all checked, with no per-request
  network call. The verified `sub` claim is the user id. With `CLERK_ISSUER` unset, the API runs in
  an explicit **dev-bypass** mode so local development and CI are unaffected.
- **Ownership (IDOR-closed).** History endpoints and trace persistence derive the user from the
  token and enforce per-session ownership, instead of trusting any client-supplied id.
- **Per-user rate limiting.** The LLM endpoints (`/api/answer`, `/api/answer/stream`,
  `/api/summarize`) are capped per user via slowapi (default `10/min`), keyed by the verified user
  id with an IP fallback. `scripts/ratelimit_test.py` burst-verifies the cap holds exactly — a
  25-request simultaneous burst resolves to **10×`200` + 15×`429`**.
- **Bounded caches.** The answer and summary caches are fixed-capacity LRU structures, so a
  long-running server cannot leak memory.

> **Operational note.** slowapi's default counter is in-memory and per-process; run the API
> single-worker for the rate limit to behave as one shared bucket. A Redis `storage_uri` is the
> path to multi-worker — see `ratelimit.py`.

---

## VII. Benchmarks & Known Constraints (read this carefully)

We evaluate with an **LLM-as-a-judge** (Groq) over 10 queries (5 semantic, 5 relational), comparing
the hybrid router's context against a **pure-vector baseline**, and measuring a token "sufficiency"
judgment. The honest results:

```
Category      Queries   Hybrid Tok   Baseline Tok   Reduction   Accuracy
─────────────────────────────────────────────────────────────────────────
semantic            5       3233.4         3189.0       -1.4%       0.0%
relational          5       3883.2         3837.0       -1.2%      40.0%
─────────────────────────────────────────────────────────────────────────
OVERALL            10       3558.3         3513.0       -1.3%      20.0%
```

These numbers are **not** flattering, and they are real. Two findings dominate:

### Token reduction ≈ 0% (−1.3%)
On this **dense, single-domain corpus**, the top-k vector chunks and the top-k graph-traversed
chunks **heavily overlap** — the graph surfaces largely the *same* evidence the vectors already
found. After **global chunk deduplication**, the two contexts reach **parity**; the residual −1.3%
is simply the small `Entity: <label> (<type>)` metadata the hybrid adds on top of the identical
chunk set. (This replaced an earlier −70% result that was a genuine bug — chunks were repeated once
*per mentioning entity*; global dedup fixed it.)

### Accuracy capped at 20% — two avoidable causes
1. **NER fallback to spaCy.** GLiNER (the designed zero-shot extractor) is blocked on this machine
   by an `onnxruntime` DLL load failure. The active spaCy fallback extracts the wrong things for
   this domain — markdown artifacts, `CARDINAL` numbers, raw timestamps — so the graph is **noisy**,
   and the judge correctly rates much of the retrieved context as insufficient.
2. **Aggressive truncation for rate limits.** Groq's free tier caps us at 6,000 TPM, so the judge
   sees only the first 5,000 characters of context. Relevant evidence past that cutoff is invisible
   to the judge, artificially depressing accuracy.

### Treat this as a baseline, not a verdict
The pipeline is **correct and fully operational** — these are *data-quality* and *environment*
constraints, not logic defects. The path to the originally-hypothesized gains:

- **Unblock GLiNER** (fix `onnxruntime` / install the MSVC redistributable) → clean domain entities
  → a meaningful graph and far higher judge accuracy.
- **Raise the judge token budget** (paid Groq tier or a local model) → remove the 5k truncation.
- **Re-scope the token-reduction comparison** to naive over-retrieval (where graph precision
  actually saves tokens), rather than equal-k vector retrieval.

---

## VIII. Quickstart

```powershell
# 1. backend install
cd backend
pip install -r requirements.txt
python -m spacy download en_core_web_sm        # fallback NER
#  .env: set GROQ_API_KEY + OPENROUTER_API_KEY               (see .env.example)
#  optional: CLERK_ISSUER + APP_DATABASE_URL to enable auth + history
#  (leave CLERK_ISSUER unset for an un-authed local dev-bypass)

# 2. ingest your datasets/ (writes memory.lbug, builds the HNSW index)
python scripts/ingest.py --datasets ./datasets --reset

# 3. evaluate (optional)
python scripts/benchmark.py            # -> results.csv + summary table

# 4. serve the API  (run AFTER ingest — single-writer DB lock; single-worker)
uvicorn api:app --reload --port 8000   # docs at /docs

# 5. run TraceRAG Studio (in a second shell)
cd ../frontend
npm install
npm run dev                            # http://localhost:5173
```

### API surface

| Method | Endpoint | Auth | Returns |
|---|---|---|---|
| POST | `/api/trace` | token | ranked nodes + `page_content` + `trace_log` + `context` |
| POST | `/api/subgraph` | — | `{ nodes, edges }` (1-hop bounded) |
| POST | `/api/answer` · `/api/answer/stream` | token + rate-limit | grounded answer (blocking / streamed) |
| POST | `/api/summarize` | token + rate-limit | one-sentence node summary |
| GET · POST | `/api/graphs` · `/api/graphs/switch` | — | list / hot-swap the active graph |
| GET | `/api/suggestions` | — | graph-aware example questions |
| POST · GET | `/api/sessions` · `/api/sessions/{id}/traces` | token (owner) | create / list sessions, fetch trace logs |
| GET | `/api/health` | — | `{ status, nodes }` |

> **Operational note.** LadybugDB is a single-writer embedded store. Don't run `ingest.py` and
> `uvicorn` against the same `.lbug` simultaneously — ingest first, then serve. The API loads the
> data snapshot at startup; re-ingest → restart the server to refresh.

---

## License

MIT.
