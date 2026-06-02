"""Central configuration for TraceRAG.

Every magic number from the architecture spec lives here so that ``db.py``,
``curation.py``, ``router.py`` and the scripts all read from one place.
Values can be overridden via environment variables where noted.
"""

from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load a local .env (e.g. GROQ_API_KEY) if present. No-op if python-dotenv is
# not installed or the file is absent — real env vars still take precedence.
try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

#: The single LadybugDB file holding both vectors and graph.
DB_PATH = Path(os.getenv("TRACERAG_DB_PATH", PROJECT_ROOT / "memory.lbug"))

#: Where ingest.py reads unstructured data from (.md / .json / .pdf).
DATASETS_DIR = Path(os.getenv("TRACERAG_DATASETS_DIR", PROJECT_ROOT / "datasets"))

#: Where benchmark.py writes results.csv.
RESULTS_CSV = Path(os.getenv("TRACERAG_RESULTS_CSV", PROJECT_ROOT / "results.csv"))


# --------------------------------------------------------------------------- #
# Embeddings  (local, 384-dim — must match the FLOAT[384] schema column)
# --------------------------------------------------------------------------- #
EMBED_MODEL = os.getenv("TRACERAG_EMBED_MODEL", "all-MiniLM-L6-v2")
EMBED_DIM = 384  # all-MiniLM-L6-v2; change this AND the schema together.


# --------------------------------------------------------------------------- #
# LLM (Groq cloud API) — deep-merge curation + router intent fallback
# --------------------------------------------------------------------------- #
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# llama3-8b-8192 was decommissioned by Groq; llama-3.1-8b-instant is the
# current fast Llama-3 model (good for YES/NO disambiguation).
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")


# --------------------------------------------------------------------------- #
# Two-tier curation thresholds (cosine similarity)
# --------------------------------------------------------------------------- #
#   sim >= FAST_MERGE_THRESHOLD               -> Fast Mode auto-merge (0 LLM calls)
#   DEEP_MERGE_THRESHOLD <= sim < FAST_MERGE  -> Deep Merge (ask Groq YES/NO)
#   sim <  DEEP_MERGE_THRESHOLD               -> create a new node
FAST_MERGE_THRESHOLD = float(os.getenv("TRACERAG_FAST_MERGE", "0.92"))
DEEP_MERGE_THRESHOLD = float(os.getenv("TRACERAG_DEEP_MERGE", "0.85"))
GREY_ZONE_LOW = DEEP_MERGE_THRESHOLD  # backward-compat alias

#: How many nearest neighbours to inspect during curation dedup search.
CURATION_TOP_K = int(os.getenv("TRACERAG_CURATION_TOP_K", "5"))


# --------------------------------------------------------------------------- #
# Intent-based hybrid router weights  (alpha = vector, beta = graph; a+b = 1)
# --------------------------------------------------------------------------- #
# Conceptual / semantic queries -> lean on vectors.
ROUTER_WEIGHTS_CONCEPTUAL = {"vector": 0.80, "graph": 0.20}
# Relational / multi-hop queries ("who", "caused by", "which PR") -> lean on graph.
ROUTER_WEIGHTS_RELATIONAL = {"vector": 0.15, "graph": 0.85}

#: Lowercase trigger tokens that flip the router into relational/multi-hop mode.
RELATIONAL_QUERY_MARKERS = (
    "who", "whom", "whose", "which", "what caused", "caused by", "because of",
    "related to", "connected to", "depends on", "owns", "owned by", "between",
    "path from", "linked to", "responsible for", "which pr", "which ticket",
)

#: Lowercase tokens that signal a broad conceptual/semantic query.
SEMANTIC_QUERY_MARKERS = (
    "explain", "architecture", "overview", "summary", "summarise", "summarize",
    "describe", "what is", "how does", "concept", "definition", "purpose of",
)

#: Top-k for the vector arm.
TOP_K_VECTOR = int(os.getenv("TRACERAG_TOP_K_VECTOR", "10"))
TOP_K_GRAPH = int(os.getenv("TRACERAG_TOP_K_GRAPH", "10"))

# Graph traversal (Stream B) tuning.
GRAPH_SEED_TOP_N = int(os.getenv("TRACERAG_GRAPH_SEED_TOP_N", "3"))
GRAPH_SEED_MIN_SIM = float(os.getenv("TRACERAG_GRAPH_SEED_MIN_SIM", "0.70"))
GRAPH_NEIGHBOR_K = int(os.getenv("TRACERAG_GRAPH_NEIGHBOR_K", "5"))
GRAPH_MAX_HOPS = int(os.getenv("TRACERAG_GRAPH_MAX_HOPS", "2"))

#: Max distinct chunk snippets appended to each retrieved entity's page_content.
RETRIEVAL_SNIPPETS_PER_NODE = int(os.getenv("TRACERAG_SNIPPETS_PER_NODE", "3"))


# --------------------------------------------------------------------------- #
# Extraction (GLiNER primary, spaCy fallback)
# --------------------------------------------------------------------------- #
GLINER_MODEL = os.getenv("TRACERAG_GLINER_MODEL", "urchade/gliner_medium-v2.1")
SPACY_MODEL = os.getenv("TRACERAG_SPACY_MODEL", "en_core_web_sm")

#: Zero-shot entity labels for the MLOps / Jira domain.
ENTITY_LABELS = ["Person", "Service", "Repo", "Ticket", "PR", "Team", "Tool"]

#: GLiNER confidence floor for keeping an extracted span.
GLINER_THRESHOLD = float(os.getenv("TRACERAG_GLINER_THRESHOLD", "0.4"))

#: GLiNER has a strict context window. We feed it WORD-based sliding windows so
#: long Markdown / Jira logs never silently drop entities past the limit.
GLINER_WINDOW_WORDS = int(os.getenv("TRACERAG_GLINER_WINDOW_WORDS", "300"))
GLINER_WINDOW_OVERLAP = int(os.getenv("TRACERAG_GLINER_WINDOW_OVERLAP", "50"))

#: Document-level text chunking (characters) for ingestion / passage storage.
CHUNK_SIZE = int(os.getenv("TRACERAG_CHUNK_SIZE", "1200"))
CHUNK_OVERLAP = int(os.getenv("TRACERAG_CHUNK_OVERLAP", "150"))


# --------------------------------------------------------------------------- #
# LadybugDB schema  (Kùzu-compatible Cypher DDL)
# --------------------------------------------------------------------------- #
# A single generic Entity node table + generic RELATES_TO edge keeps the schema
# dynamic across all GLiNER labels (the `type` column carries the label).
NODE_TABLE = "Entity"
REL_TABLE = "RELATES_TO"          # Entity -> Entity (same-window co-occurrence)
DOC_TABLE = "Document"           # source document node (no embedding)
MENTIONS_TABLE = "MENTIONS"      # Document -> Entity
VECTOR_INDEX = "idx_entity_embedding"
VECTOR_METRIC = "cosine"
