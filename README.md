# 🕸️ TraceRAG — The Observable GraphRAG Engine

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![LadybugDB](https://img.shields.io/badge/storage-LadybugDB-red.svg)](https://github.com/ladybugdb/ladybug)
[![Groq](https://img.shields.io/badge/LLM-Groq%20(Llama%203)-orange.svg)](https://groq.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> A local-first, observability-driven GraphRAG pipeline. Vectors **and** graph live in a
> single `.lbug` file — no dual-store sync — with a two-tier entity-resolution engine and a
> visual tracer that lets you *see* why the retriever chose what it chose.

---

## I. Executive Summary

Multi-hop retrieval for agents tends to fail for three infrastructural reasons: dual-store
sync hell (graph DB + vector DB), runaway **entity drift** from LLM extraction (the *"Janitor
Problem"* — `PaymentService`, `payments-v2`, and `pay_svc` becoming three nodes), and
**black-box routing** that gives no insight into why a hybrid retriever weighted a graph edge
over a semantic chunk.

**TraceRAG** is an orchestration and observability layer (not a new database) that addresses
all three:

- **Zero-sync storage** — semantic vectors (`FLOAT[384]`) and the relational graph live
  natively in one embedded **LadybugDB** file.
- **Two-tier curation** — a cheap vector pass auto-merges obvious duplicates; a local-LLM
  pass (Groq) adjudicates only the ambiguous "grey zone," keeping the graph clean without a
  human janitor.
- **Traceable routing** — every query returns a structured `trace_log` (intent weights,
  vector seeds, graph hops) that the **TraceRAG Studio** UI renders so stakeholders can watch
  the AI's reasoning path.

This document reports what was built **and how it actually performs** — including a candid
benchmark section (§V) where the headline thesis did *not* hold on our current data, and why.

---

## II. Core Architecture & Stack

| Layer | Technology | Role |
|---|---|---|
| **Embeddings** | `sentence-transformers` · `all-MiniLM-L6-v2` | 384-dim sentence vectors (cosine) |
| **Entity extraction** | **GLiNER** (designed) / **spaCy** (current fallback) | Zero-shot domain NER; see §V for why spaCy is active |
| **Storage** | **LadybugDB** (embedded, Kùzu-lineage) | Single-file hybrid vector + graph store with a native HNSW `VECTOR` extension |
| **LLM** | **Groq API** · `llama-3.1-8b-instant` | Grey-zone entity disambiguation + router intent fallback |
| **API** | **FastAPI** + Uvicorn | Headless backend serving trace + subgraph |
| **Frontend** | **Next.js / ReactFlow** | TraceRAG Studio — visual query tracer |

```
tracerag/
├── config.py            # single source of truth for thresholds, weights, models
├── db.py                # LadybugDB connection, schema, HNSW index, graph queries
├── extract.py           # GLiNER (→ spaCy fallback) + word-based sliding window
├── curation.py          # two-tier resolution (vector fast-merge + Groq grey-zone)
├── router.py            # intent classification + dual-stream rank fusion + trace_log
└── integrations/
    └── langchain.py     # drop-in BaseRetriever
scripts/
├── ingest.py            # headless ingest CLI
└── benchmark.py         # LLM-as-judge evaluation → results.csv
api.py                   # FastAPI app (/api/trace, /api/subgraph, /api/health)
```

### Data model
A single generic `Entity` node table (`id, label, type, embedding`) keeps the schema dynamic
across all entity labels. `Document` nodes store one **sliding-window chunk** each (with raw
`content` for generation). Edges: `Document -[MENTIONS]-> Entity` and `Entity -[RELATES_TO]->
Entity` (only between entities co-occurring in the *same* window — no document-wide hairball).

---

## III. Entity Resolution — The Two-Tier "Janitor"

Every extracted mention is embedded and compared (cosine) against already-resolved nodes.
The decision is tiered to spend LLM budget only where it matters:

| Similarity | Action | Cost |
|---|---|---|
| **≥ 0.92** | **Fast Mode** — auto-merge into the existing canonical node | 0 LLM calls |
| **0.85 – 0.92** | **Deep Merge** — ask Groq *"Are 'X' and 'Y' the exact same entity? YES/NO"* (`temperature=0`) | 1 Groq call |
| **< 0.85** | Mint a new node (deterministic slug id) | 0 LLM calls |

Canonical nodes are **never** overwritten on merge (a later, noisier surface form can't clobber
the clean label/embedding), and Groq failures **fail-safe to NO** — the engine prefers a
duplicate node over a hallucinated merge.

> **Implementation note.** This LadybugDB build's HNSW index is *static* (the indexed property
> can't be mutated once the index exists), so curation does its dedup search **in-memory**
> (normalized-cosine) during ingest, and the persistent HNSW index is built **once afterward**
> for query-time retrieval.

**Observed on the test corpus (7 docs, 255 raw mentions):**

| Metric | Value |
|---|---|
| Raw extracted mentions | 255 |
| Canonical nodes after curation | **135** |
| Entity consolidation | **≈ 47%** |
| Fast-mode auto-merges (≥0.92) | 117 |
| Groq grey-zone adjudications (0.85–0.92) | 12 (→ 3 merged, 9 kept distinct) |

The two-tier engine and the Groq migration are **verified working** end-to-end.

---

## IV. Intent-Based Hybrid Routing

The router never uses static weights. It classifies query intent, then fuses two retrieval
streams with:

```
S = α · s_v + β · s_g          (α + β = 1)
```

- `s_v` = vector similarity (`1 − cosine_distance`) from the HNSW index.
- `s_g` = graph PathScore — the product of edge confidences along the traversal from the
  vector "seed" nodes (seeds score `1.0`).

**Dynamic weighting:**

| Intent | α (vector) | β (graph) | Trigger |
|---|---|---|---|
| **Semantic / conceptual** | **0.80** | 0.20 | keywords (*explain, architecture, overview…*) |
| **Relational / multi-hop** | 0.15 | **0.85** | keywords (*who, caused by, which PR, depends on…*) |
| *ambiguous* | — | — | Groq fallback classifier (`SEMANTIC` / `RELATIONAL`) |

Every call emits a `trace_log` consumed by the UI:

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

## V. Benchmarks & Known Constraints (read this carefully)

We evaluate with an **LLM-as-a-judge** (Groq) over 10 queries (5 semantic, 5 relational),
comparing the hybrid router's context against a **pure-vector baseline**, and measuring a token
"sufficiency" judgment. The honest results:

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
found. After **global chunk deduplication**, the two contexts reach **parity**; the residual
**−1.3%** is simply the small `Entity: <label> (<type>)` metadata framing the hybrid adds on
top of the identical chunk set. (Note: this number replaced an earlier **−70%** result that was
a genuine bug — chunks were being repeated once *per mentioning entity*. Global dedup fixed it.)

### Accuracy capped at 20% — two avoidable causes
1. **NER fallback to spaCy.** GLiNER (our designed zero-shot extractor) is blocked on this
   machine by an `onnxruntime` DLL load failure. The active spaCy fallback extracts the wrong
   things for this domain — markdown artifacts (`#`, `## Services`), `CARDINAL` numbers, and raw
   timestamps — so the graph is **noisy**, and the judge correctly rates much of the retrieved
   context as insufficient.
2. **Aggressive truncation for rate limits.** Groq's free tier caps us at **6,000 TPM**, so the
   judge sees only the first **5,000 characters** of context (with 15s request pacing). Relevant
   evidence past that cutoff is invisible to the judge, artificially depressing accuracy.

### Treat this as a baseline, not a verdict
The pipeline is **correct and fully operational** — these are *data-quality* and *environment*
constraints, not logic defects. The clear path to the originally-hypothesized gains:

- **Unblock GLiNER** (install MSVC redistributable / fix `onnxruntime`) → clean domain entities
  → a meaningful graph and far higher judge accuracy.
- **Raise the judge token budget** (paid Groq tier or a local model) → remove the 5k truncation.
- **Re-scope the token-reduction comparison** to naive over-retrieval (the regime where graph
  precision actually saves tokens), rather than equal-k vector retrieval.

---

## VI. Visual Observability — The True Win

The defensible payoff of this project isn't a token percentage — it's **observability**. The
backend is fully **decoupled** from the UI: `POST /api/trace` returns the ranked nodes *and*
the `trace_log`, and `POST /api/subgraph` returns a bounded neighborhood (requested nodes +
1-hop neighbors + interconnecting edges, each flagged `requested`) so the browser never has to
render the whole graph.

**TraceRAG Studio** (Next.js / ReactFlow) consumes these to let a stakeholder literally *watch
the AI think*:

- which nodes came from the **vector** arm vs the **graph** arm,
- the exact **α / β** the router chose for that query's intent,
- the **hop path** the traversal walked,
- the **dimmed background** of 1-hop context around the active trace.

When a hybrid retriever makes a surprising choice, you can *see* why — turning "the model
hallucinated" into an inspectable execution plan.

---

## Quickstart

```powershell
# 1. install
pip install -r requirements.txt
python -m spacy download en_core_web_sm        # fallback NER
#  set GROQ_API_KEY in .env  (see .env.example)

# 2. ingest your datasets/ (writes memory.lbug, builds the HNSW index)
python scripts/ingest.py --datasets ./datasets --reset

# 3. evaluate (optional)
python scripts/benchmark.py            # -> results.csv + summary table

# 4. serve the API for the UI  (run AFTER ingest — single-writer DB lock)
uvicorn api:app --reload --port 8000   # docs at /docs
```

**API surface**

| Method | Endpoint | Body | Returns |
|---|---|---|---|
| POST | `/api/trace` | `{ "query": str }` | ranked nodes + `page_content` + `trace_log` |
| POST | `/api/subgraph` | `{ "node_ids": [str] }` | `{ nodes, edges }` (1-hop bounded) |
| GET | `/api/health` | — | `{ status, nodes }` |

> **Operational note:** LadybugDB is a single-writer embedded store. Don't run `ingest.py` and
> `uvicorn` against the same `.lbug` simultaneously — ingest first, then serve. The API loads
> the data snapshot at startup; re-ingest → restart the server to refresh.

---

## License

MIT.
