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

The single idea the whole project is built around: **one hybrid store, queried by two arms
(vector + graph), fused by intent.**

```mermaid
flowchart TB
  %% ---------- 1 · INGESTION ----------
  subgraph INGEST["1 · Ingestion pipeline (offline CLI)"]
    direction TB
    DOC["Source doc<br/>'PR #N merged by AUTHOR. Title… Description…'"]
    DOC --> WIN["sliding_window_words<br/>300-word windows · 50 overlap"]
    WIN --> NER["GLiNER zero-shot NER<br/>Person · Service · Library · PR<br/>Ticket · Team · Tool<br/>(spaCy ruler fallback)"]
    NER --> MEMB["embed each mention<br/>MiniLM · 384-dim · normalized"]
    MEMB --> CUR1{"cosine vs<br/>existing nodes"}
    CUR1 -->|"≥ 0.92"| FAST["fast auto-merge<br/>0 LLM"]
    CUR1 -->|"0.85 – 0.92"| DEEP["Groq · same entity?<br/>YES / NO · fail-safe NO"]
    CUR1 -->|"under 0.85"| NEW["mint new node<br/>slug id"]
    DEEP -->|YES| FAST
    DEEP -->|NO| NEW
  end

  %% ---------- 2 · HYBRID STORE ----------
  subgraph SCHEMA["2 · LadybugDB — single .lbug (vectors + graph)"]
    direction LR
    ENT[("Entity<br/>id · label · type<br/>embedding FLOAT 384")]
    DOCN[("Document<br/>id · path · content")]
    ENT -->|"RELATES_TO · confidence"| ENT
    DOCN -->|MENTIONS| ENT
    HNSW["HNSW vector index<br/>on Entity.embedding"]
    ENT --- HNSW
  end
  FAST --> ENT
  NEW --> ENT
  MEMB -. "document + edges" .-> DOCN

  %% ---------- 3 · QUERY ----------
  Q(["User query"]) --> IC["classify_intent"]
  IC -->|"keyword markers"| W["alpha / beta weights"]
  IC -->|"ambiguous"| GROQI["Groq · SEMANTIC / RELATIONAL"]
  GROQI --> W

  subgraph VEC["3a · Vector arm — semantic"]
    direction TB
    QE["embed_query · MiniLM"] --> VS["QUERY_VECTOR_INDEX (HNSW)<br/>top-k pool · similarity s_v"]
  end

  subgraph GRAPH["3b · Graph arm — relational"]
    direction TB
    SEEDL["linked seeds<br/>spaCy ruler → find_nodes_by_label"]
    SEEDF["fuzzy seeds<br/>cosine ≥ 0.35 · top-3"]
    SEEDL --> SD["seed set · dedup"]
    SEEDF --> SD
    SD --> EF["expand_frontier<br/>ONE query per hop · no N+1"]
    EF --> HUB["hub throttle<br/>skip degree above MAX_DEGREE"]
    HUB --> PS["path_score =<br/>product of edge confidences"]
    PS --> HOPQ{"hop below MAX_HOPS<br/>and frontier left?"}
    HOPQ -->|yes| EF
    HOPQ -->|no| GG["graph_scores s_g + hops"]
  end

  W --> QE
  W --> SEEDL
  VS --> SEEDF
  QE -. reads .-> HNSW
  VS -. reads .-> ENT
  EF -. traverses .-> ENT

  VS --> FUSE["Fusion · S = alpha·s_v + beta·s_g<br/>dynamic vector_k throttle by graph hits<br/>rank → top_k nodes"]
  GG --> FUSE
  FUSE --> AD["attach_documents · via MENTIONS"]
  AD -. reads .-> DOCN
  AD --> BC["build_context<br/>dedup chunks · graph traces first"]
  BC --> GEN["Grounded generation<br/>OpenRouter · context-only · streamed"]
  GEN --> OUT(["answer + per-node score pills<br/>+ trace_log → ReactFlow canvas"])
```

**The GraphRAG story in five lines**
1. **One hybrid store, no sync.** LadybugDB holds *both* the 384-dim embeddings *and* the relationship graph in a single `.lbug` — no graph-DB ↔ vector-DB consistency problem.
2. **Ingestion builds the graph.** Docs → GLiNER typed entities → two-tier curation dedupes → entities, embeddings, and `RELATES_TO` / `MENTIONS` edges land in the store.
3. **Two arms read the same store.** A query fans into a **vector arm** (semantic similarity via HNSW) and a **graph arm** (multi-hop traversal over `RELATES_TO`, scoring paths by the product of edge confidences).
4. **Intent decides the blend.** The classifier sets `alpha/beta`; fusion combines them as `S = alpha·s_v + beta·s_g`. "Who caused X?" leans graph; "explain X" leans vector.
5. **Why it beats plain RAG.** Embeddings find *similar text*; the graph arm follows *relationships* — surfacing the PR / person / service connected to the answer even when the words don't match.

### Stack

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

### High-Level Design (HLD)

```mermaid
flowchart LR
  subgraph CLIENT["TraceRAG Studio — Vite + React + ReactFlow"]
    direction TB
    UI["Visual canvas<br/>traced path · score pills · hover"]
    AC["Answer card<br/>streamed + clickable citations"]
    CK["Clerk SDK<br/>getToken bridge"]
  end

  CLERK[("Clerk<br/>Auth Provider / JWKS")]

  subgraph BACKEND["FastAPI Backend"]
    direction TB
    CORS["CORS"]
    AUTH["Auth dependency<br/>PyJWT + JWKS verify"]
    RL["slowapi rate limiter<br/>per-user 10/min"]
    ROUTER["TraceRouter<br/>intent-weighted hybrid retrieval"]
    GEN["Answer / Summarize<br/>grounded · streamed · cached"]
    HIST["History API<br/>ownership-checked"]
    CACHE[("LRU caches")]
  end

  subgraph LOCAL["Local models (in-process)"]
    direction TB
    EMB["sentence-transformers<br/>all-MiniLM-L6-v2 · 384-dim"]
    RULER["spaCy ruler<br/>query-side entity linking"]
  end

  subgraph DATA["Data stores"]
    direction TB
    LBUG[("LadybugDB<br/>vectors + graph in one .lbug<br/>HNSW vector index")]
    PG[("Neon Postgres<br/>users · chat sessions · trace logs")]
  end

  subgraph EXT["External LLMs"]
    direction TB
    GROQ["Groq · llama-3.1-8b-instant<br/>intent + grey-zone merge"]
    OR["OpenRouter · claude-3-haiku<br/>answers + summaries"]
  end

  subgraph INGESTHLD["Offline ingestion (CLI)"]
    direction TB
    GH[("GitHub API<br/>merged PRs")]
    GLINER["GLiNER zero-shot NER<br/>spaCy fallback"]
    CUR["Two-tier curation"]
  end

  CK -->|sign in| CLERK
  UI -->|"query + Bearer JWT"| CORS
  AC -->|"answer + Bearer JWT"| CORS
  CORS --> AUTH
  AUTH -->|verify| CLERK
  AUTH --> RL
  RL --> ROUTER
  RL --> HIST
  RL --> GEN
  ROUTER --> EMB
  ROUTER --> RULER
  ROUTER --> LBUG
  ROUTER --> GROQ
  GEN --> CACHE
  GEN --> OR
  GEN -->|SSE tokens| AC
  ROUTER -->|subgraph| UI
  HIST --> PG

  GH --> GLINER --> CUR
  CUR -->|nodes + edges| LBUG
  CUR -->|adjudicate| GROQ
```

- Every request crosses **CORS → Auth (JWT verify against Clerk's JWKS) → per-user rate limit** before any business logic.
- The retrieval core (`TraceRouter`) reads the **single hybrid store (LadybugDB)**, embeds locally (no network for embeddings), and calls **Groq** only for the cheap intent decision.
- Generation is a **separate, cached, streamed** path to **OpenRouter** — off the retrieval critical path. **History** is independent (Postgres), and **ingestion is fully offline**.

### Low-Level Design — query & retrieval pipeline (`POST /api/trace`)

```mermaid
flowchart TB
  START(["POST /api/trace<br/>{ query, top_k, session_id }"])

  subgraph SEC["Security chain"]
    direction TB
    A1["extract Bearer token"] --> A2["JWKS: resolve public key by kid"]
    A2 --> A3["verify RS256 sig + exp / iss / azp"]
    A3 --> A4["sub → request.state.user_id"]
    A4 --> A5["slowapi: bucket = user_id<br/>10/min else HTTP 429"]
  end

  START --> A1
  A5 --> I1

  subgraph ROUTE["TraceRouter.route — recall"]
    direction TB
    I1["classify_intent<br/>keyword markers (free)"] -->|ambiguous| I2["Groq fallback<br/>SEMANTIC / RELATIONAL"]
    I1 --> W["alpha, beta weights"]
    I2 --> W
    W --> E["embed_query<br/>MiniLM 384-dim, normalized"]
    E --> V["vector_hits<br/>CALL QUERY_VECTOR_INDEX (HNSW)<br/>pool = (id, similarity)"]
    V --> S1["linked seeds<br/>spaCy ruler → find_nodes_by_label"]
    V --> S2["fuzzy seeds<br/>cosine ≥ min_sim, top-N"]
    S1 --> S["seeds (dedup)"]
    S2 --> S
  end

  S --> B1

  subgraph BFS["graph_stream — multiplicative BFS, per hop"]
    direction TB
    B1["expand_frontier(frontier)<br/>ONE query per hop (no N+1)"] --> B2["hub throttle:<br/>skip nodes with degree above MAX_DEGREE"]
    B2 --> B3["path_score = product of edge confidences<br/>keep max score per node"]
    B3 --> B4{"more hops left<br/>and frontier not empty?"}
    B4 -->|yes| B1
    B4 -->|no| BOUT["graph_scores + hops"]
  end

  subgraph ASSEMBLE["Fuse & assemble"]
    direction TB
    F["fuse: S = alpha·s_v + beta·s_g<br/>throttle vector_k by graph hits<br/>rank → top_k"]
    F --> D["attach_documents<br/>via MENTIONS edges"]
    D --> C["build_context<br/>dedup chunks · traces first"]
  end

  BOUT --> F
  C --> OUT(["results + trace_log + context"])

  E -. uses .-> EMB[("MiniLM (local)")]
  V -. reads .-> LBUG[("LadybugDB")]
  B1 -. reads .-> LBUG
  D -. reads .-> LBUG
  I2 -. calls .-> GROQ[("Groq")]

  OUT --> SUB["POST /api/subgraph<br/>1-hop neighborhood → ReactFlow canvas"]
  OUT -. "if session_id" .-> PERSIST[("persist_trace → Postgres<br/>ownership-checked")]
  OUT --> ANS["POST /api/answer/stream"]

  subgraph GENF["Answer generation"]
    direction TB
    G1{"LRU hit?<br/>key = (query, context)"} -->|hit| G3["stream cached text"]
    G1 -->|miss| G2["OpenRouter (stream)<br/>grounded, context-only prompt"]
    G2 --> G3
  end

  ANS --> G1
  G3 --> TOK["SSE tokens → Answer card<br/>→ clickable citations"]
```

1. **Security first.** Auth + rate limit run as dependencies *before* the handler; the verified `sub` is stashed on `request.state` so the limiter keys per user.
2. **Intent is two-tier.** Keyword markers decide most queries for free; only ambiguous ones pay a fast Groq call. Intent sets the fusion weights.
3. **Two recall arms.** Vector arm hits HNSW; graph arm seeds from links + fuzzy hits, then runs a **batched BFS** (one DB query per hop), scoring paths by the product of edge confidences, with hubs throttled.
4. **Fusion + assembly.** `S = alpha·s_v + beta·s_g`; documents pulled via `MENTIONS`, de-duplicated into the final context.
5. **Generation is decoupled.** Canvas (`/api/subgraph`) and streamed answer (`/api/answer/stream`, LRU-cached) are separate calls — the LLM never blocks retrieval.

### Low-Level Design — ingestion & curation pipeline (offline)

```mermaid
flowchart TB
  GH[("GitHub API<br/>/repos/{repo}/pulls?state=closed")] --> FETCH["fetch_merged_prs<br/>page, keep merged_at != null, limit 50"]
  FETCH --> ASM["assemble_text<br/>'PR #N merged by AUTHOR. Title… Description…'<br/>strip markdown / HTML"]
  ASM --> WIN["sliding_window_words<br/>300-word windows, 50 overlap"]
  WIN --> NER["GLiNER zero-shot NER<br/>Person · Service · Library · PR · Ticket · Team · Tool<br/>(spaCy ruler fallback)"]
  NER --> MEMB["embed each mention<br/>MiniLM 384-dim"]
  MEMB --> C1

  subgraph CURING["Two-tier curation — per mention"]
    direction TB
    C1{"cosine vs existing nodes"}
    C1 -->|"≥ 0.92"| C2["fast auto-merge<br/>0 LLM calls"]
    C1 -->|"0.85 – 0.92"| C3["Groq: same entity? YES / NO<br/>fail-safe to NO"]
    C1 -->|"under 0.85"| C4["mint new node<br/>deterministic slug id"]
    C3 -->|YES| C2
    C3 -->|NO| C4
  end

  C2 --> UP
  C4 --> UP
  UP["upsert nodes (never clobber canonical)<br/>RELATES_TO = same-window co-occurrence<br/>Document → Entity via MENTIONS<br/>store PR url as source"] --> IDX["build_vector_index<br/>HNSW over embeddings (once, post-ingest)"]
  IDX --> OUTDB[("graphs/{owner}__{repo}.lbug")]

  C3 -. calls .-> GROQ2[("Groq")]
```

- Each merged PR becomes one document; entities are extracted **per sliding window** so long bodies don't lose tail entities.
- The **"Janitor"** is the two-tier curation: cosine auto-merges obvious duplicates; only the grey zone (0.85–0.92) costs a Groq call, which **fails safe to NO**.
- The HNSW index is built **once after** ingestion (the index is static and can't be mutated while embeddings are written).

### End-to-end request sequence

```mermaid
sequenceDiagram
  autonumber
  participant U as Browser Studio
  participant A as FastAPI auth+ratelimit
  participant R as TraceRouter
  participant L as LadybugDB
  participant G as Groq
  participant O as OpenRouter
  participant P as Postgres

  U->>A: POST /api/trace (query + Bearer JWT)
  A->>A: verify JWT via JWKS, set user_id
  A->>A: rate-limit bucket(user_id)
  A->>R: route(query)
  R->>R: classify intent (keyword markers)
  opt ambiguous
    R->>G: classify SEMANTIC / RELATIONAL
    G-->>R: intent
  end
  R->>L: vector_hits (HNSW)
  L-->>R: pool
  loop per hop (up to MAX_HOPS)
    R->>L: expand_frontier (batched, 1 query)
    L-->>R: neighbors + confidences
  end
  R->>L: documents_for_entities (MENTIONS)
  L-->>R: chunks
  R-->>A: results + trace_log + context
  opt session_id present
    A->>P: persist_trace (ownership-checked)
  end
  A-->>U: trace payload

  U->>A: POST /api/subgraph (node_ids)
  A->>L: 1-hop neighborhood
  L-->>A: nodes + edges
  A-->>U: nodes + edges (canvas render)

  U->>A: POST /api/answer/stream (query, context)
  alt LRU cache hit
    A-->>U: stream cached answer
  else cache miss
    A->>O: grounded prompt (context only)
    O-->>A: token stream
    A-->>U: SSE tokens
  end
  U->>U: click citation, then pan / zoom / highlight node
```

### Component reference

| Component | Responsibility | Key files |
|---|---|---|
| TraceRouter | Intent classification, dual-arm retrieval, fusion, context assembly | `tracerag/router.py` |
| TraceDB | LadybugDB schema, HNSW, batched graph queries | `tracerag/db.py` |
| EntityExtractor | GLiNER (→ spaCy) over sliding windows | `tracerag/extract.py` |
| CurationEngine | Two-tier entity resolution | `tracerag/curation.py` |
| Auth | Clerk JWT verification (PyJWT + JWKS) + dev-bypass | `auth.py` |
| Rate limiter | Per-user slowapi limiter | `ratelimit.py` |
| LRU caches | Bounded answer / summary caches | `cache.py` |
| History | Sessions + trace logs, ownership-checked | `routers/history.py`, `models.py` |
| API | FastAPI app + endpoints | `api.py` |
| Studio | Visual tracer, answer card, citations | `frontend/src/` |

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
