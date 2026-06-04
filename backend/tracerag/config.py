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

# Load a local .env (e.g. OPENROUTER_API_KEY) if present. No-op if python-dotenv is
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
# LLM (OpenRouter, OpenAI-compatible) — deep-merge curation, router intent,
# and the benchmark judge. High-context models let us drop judge truncation.
# --------------------------------------------------------------------------- #
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
#: Any OpenRouter model slug — e.g. "google/gemini-flash-1.5" or
#: "anthropic/claude-3-haiku". Verify the exact slug on openrouter.ai/models.
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3-haiku")
#: OpenRouter-recommended attribution headers.
OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL",
                                "https://github.com/Kcodess2807/TraceRAG")
OPENROUTER_APP_TITLE = os.getenv("OPENROUTER_APP_TITLE", "TraceRAG")


# --------------------------------------------------------------------------- #
# Two-tier curation thresholds (cosine similarity)
# --------------------------------------------------------------------------- #
#   sim >= FAST_MERGE_THRESHOLD               -> Fast Mode auto-merge (0 LLM calls)
#   DEEP_MERGE_THRESHOLD <= sim < FAST_MERGE  -> Deep Merge (ask the LLM YES/NO)
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
GRAPH_SEED_MIN_SIM = float(os.getenv("TRACERAG_GRAPH_SEED_MIN_SIM", "0.35"))
GRAPH_NEIGHBOR_K = int(os.getenv("TRACERAG_GRAPH_NEIGHBOR_K", "5"))
GRAPH_MAX_HOPS = int(os.getenv("TRACERAG_GRAPH_MAX_HOPS", "2"))
#: Do NOT traverse through hub super-nodes (degree > MAX_DEGREE) — they connect
#: to nearly everything and flood the context with irrelevant neighbors.
MAX_DEGREE = int(os.getenv("TRACERAG_MAX_DEGREE", "10"))


# --------------------------------------------------------------------------- #
# Extraction (GLiNER primary, spaCy fallback)
# --------------------------------------------------------------------------- #
GLINER_MODEL = os.getenv("TRACERAG_GLINER_MODEL", "urchade/gliner_medium-v2.1")
SPACY_MODEL = os.getenv("TRACERAG_SPACY_MODEL", "en_core_web_sm")

#: Zero-shot entity labels for the MLOps / Jira domain. "Repo" dropped — in a
#: microservices context Service/Tool/Library carry the topology, while "Repo"
#: mostly mis-caught filenames (ctx.py) and version strings, adding noise.
ENTITY_LABELS = ["Person", "Service", "Library", "Ticket", "PR", "Team", "Tool"]

# --- spaCy fallback ontology enforcement ---------------------------------- #
# The spaCy fallback over-extracts (dates, numbers, markdown symbols), creating
# "hairball" super-nodes. Only high-signal label types survive — the statistical
# NER labels plus the deterministic EntityRuler labels (TICKET/PULL_REQUEST/SERVICE).
SPACY_ALLOWED_LABELS = ("PERSON", "ORG", "PRODUCT", "GPE",
                        "TICKET", "PULL_REQUEST", "SERVICE")
SPACY_BLOCKED_LABELS = ("CARDINAL", "DATE", "TIME", "PERCENT", "MONEY",
                        "QUANTITY", "ORDINAL")
#: Reject extracted spans shorter than this many characters.
MIN_ENTITY_CHARS = int(os.getenv("TRACERAG_MIN_ENTITY_CHARS", "3"))

#: GLiNER confidence floor for keeping an extracted span. 0.55 is the sweet
#: spot that slices off generic terms (app, issues, stable) and weak title
#: fragments while keeping high-confidence hits (usernames, frameworks).
GLINER_THRESHOLD = float(os.getenv("TRACERAG_GLINER_THRESHOLD", "0.55"))

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
