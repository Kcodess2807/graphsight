"""Central configuration for TraceRAG."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# load local .env if present; real env vars still win
try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

DB_PATH = Path(os.getenv("TRACERAG_DB_PATH", PROJECT_ROOT / "memory.lbug"))
DATASETS_DIR = Path(os.getenv("TRACERAG_DATASETS_DIR", PROJECT_ROOT / "datasets"))
RESULTS_CSV = Path(os.getenv("TRACERAG_RESULTS_CSV", PROJECT_ROOT / "results.csv"))


EMBED_MODEL = os.getenv("TRACERAG_EMBED_MODEL", "all-MiniLM-L6-v2")
EMBED_DIM = 384  # must match the FLOAT[384] schema column

# Concurrency: LadybugDB parallelizes reads across connections (it releases the
# GIL in C++), so a small pool of read connections removes the single-connection
# convoy seen under load. Writes stay on one dedicated connection (single-writer).
DB_POOL_SIZE = int(os.getenv("TRACERAG_DB_POOL_SIZE", "10"))
DB_POOL_TIMEOUT = float(os.getenv("TRACERAG_DB_POOL_TIMEOUT", "15"))  # s to wait for a free conn
# Embedding is CPU-heavy; bound concurrent encodes so they can't starve request
# threads. torch releases the GIL during encode, so threads (not processes) suffice.
EMBED_WORKERS = int(os.getenv("TRACERAG_EMBED_WORKERS", "4"))
# Query-side entity extraction (spaCy) is GIL-bound; cache results so repeated
# queries skip it. 0 disables (ingest path). Bounded LRU — no unbounded growth.
QUERY_EXTRACT_CACHE = int(os.getenv("TRACERAG_QUERY_EXTRACT_CACHE", "512"))
# Cap query length before retrieval. spaCy work grows with input size, so an
# oversized query is a CPU-DoS (a 50 KB query stalled a worker for ~90s in
# testing). Real questions are short; truncate the rest. Guards embed + extract.
MAX_QUERY_CHARS = int(os.getenv("TRACERAG_MAX_QUERY_CHARS", "2000"))

# CORS allow-list. "*" (default) accepts any origin — fine for local/dev. In
# production set CORS_ORIGINS to your frontend origin(s), comma-separated,
# e.g. "https://tracerag.vercel.app".
CORS_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()
] or ["*"]

# Sentry error tracking + performance monitoring. Fully optional: unset DSN =
# disabled, so local/dev runs are untouched. traces_sample_rate is 1.0 (trace
# everything) in dev; scale down in production (e.g. 0.1) to cap overhead/cost.
SENTRY_DSN = os.getenv("SENTRY_DSN")
SENTRY_ENABLED = bool(SENTRY_DSN)
SENTRY_ENVIRONMENT = os.getenv("SENTRY_ENVIRONMENT", "development")
SENTRY_TRACES_SAMPLE_RATE = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "1.0"))


OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3-haiku")
OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL",
                                "https://github.com/Kcodess2807/TraceRAG")
OPENROUTER_APP_TITLE = os.getenv("OPENROUTER_APP_TITLE", "TraceRAG")

# groq for the latency-critical router intent call; falls back to openrouter if unset
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")


# --- Clerk auth (backend token verification) ---
# CLERK_ISSUER is your Clerk instance URL, e.g. https://your-app.clerk.accounts.dev
# (production: your custom Clerk domain). Leave it UNSET for local dev and the API
# runs in dev-bypass mode — no token required. Set it and auth is enforced.
CLERK_ISSUER = os.getenv("CLERK_ISSUER")
# JWKS = Clerk's published public keys. Defaults to the standard well-known path
# under the issuer; override only if you proxy it somewhere else.
CLERK_JWKS_URL = os.getenv("CLERK_JWKS_URL") or (
    f"{CLERK_ISSUER.rstrip('/')}/.well-known/jwks.json" if CLERK_ISSUER else None
)
# Optional allow-list of authorized parties (the `azp` claim = the frontend
# origin a token was minted for). Comma-separated, e.g. "http://localhost:5173".
CLERK_AUTHORIZED_PARTIES = tuple(
    p.strip()
    for p in os.getenv("CLERK_AUTHORIZED_PARTIES", "").split(",")
    if p.strip()
)
# Auth is enforced only when an issuer is configured.
CLERK_ENABLED = bool(CLERK_ISSUER)
# The user id every request runs as in dev-bypass mode (Clerk unconfigured).
DEV_USER_ID = os.getenv("TRACERAG_DEV_USER_ID", "dev-user")


# two-tier curation thresholds (cosine sim): >=fast auto-merge, >=deep ask llm, else new node
FAST_MERGE_THRESHOLD = float(os.getenv("TRACERAG_FAST_MERGE", "0.92"))
DEEP_MERGE_THRESHOLD = float(os.getenv("TRACERAG_DEEP_MERGE", "0.85"))
GREY_ZONE_LOW = DEEP_MERGE_THRESHOLD  # backward-compat alias

CURATION_TOP_K = int(os.getenv("TRACERAG_CURATION_TOP_K", "5"))


# hybrid router weights (vector + graph = 1)
ROUTER_WEIGHTS_CONCEPTUAL = {"vector": 0.80, "graph": 0.20}
ROUTER_WEIGHTS_RELATIONAL = {"vector": 0.15, "graph": 0.85}

RELATIONAL_QUERY_MARKERS = (
    "who", "whom", "whose", "which", "what caused", "caused by", "because of",
    "related to", "connected to", "depends on", "owns", "owned by", "between",
    "path from", "linked to", "responsible for", "which pr", "which ticket",
)

SEMANTIC_QUERY_MARKERS = (
    "explain", "architecture", "overview", "summary", "summarise", "summarize",
    "describe", "what is", "how does", "concept", "definition", "purpose of",
)

TOP_K_VECTOR = int(os.getenv("TRACERAG_TOP_K_VECTOR", "10"))
TOP_K_GRAPH = int(os.getenv("TRACERAG_TOP_K_GRAPH", "10"))

GRAPH_SEED_TOP_N = int(os.getenv("TRACERAG_GRAPH_SEED_TOP_N", "3"))
GRAPH_SEED_MIN_SIM = float(os.getenv("TRACERAG_GRAPH_SEED_MIN_SIM", "0.35"))
GRAPH_NEIGHBOR_K = int(os.getenv("TRACERAG_GRAPH_NEIGHBOR_K", "5"))
GRAPH_MAX_HOPS = int(os.getenv("TRACERAG_GRAPH_MAX_HOPS", "2"))
MAX_DEGREE = int(os.getenv("TRACERAG_MAX_DEGREE", "10"))  # skip hub nodes above this degree


GLINER_MODEL = os.getenv("TRACERAG_GLINER_MODEL", "urchade/gliner_medium-v2.1")
SPACY_MODEL = os.getenv("TRACERAG_SPACY_MODEL", "en_core_web_sm")

ENTITY_LABELS = ["Person", "Service", "Library", "Ticket", "PR", "Team", "Tool"]

# spaCy fallback over-extracts, so allow/block lists keep only high-signal labels
SPACY_ALLOWED_LABELS = ("PERSON", "ORG", "PRODUCT", "GPE",
                        "TICKET", "PULL_REQUEST", "SERVICE")
SPACY_BLOCKED_LABELS = ("CARDINAL", "DATE", "TIME", "PERCENT", "MONEY",
                        "QUANTITY", "ORDINAL")
MIN_ENTITY_CHARS = int(os.getenv("TRACERAG_MIN_ENTITY_CHARS", "3"))

GLINER_THRESHOLD = float(os.getenv("TRACERAG_GLINER_THRESHOLD", "0.55"))

# word-based sliding window so long docs don't drop entities past gliner's limit
GLINER_WINDOW_WORDS = int(os.getenv("TRACERAG_GLINER_WINDOW_WORDS", "300"))
GLINER_WINDOW_OVERLAP = int(os.getenv("TRACERAG_GLINER_WINDOW_OVERLAP", "50"))

CHUNK_SIZE = int(os.getenv("TRACERAG_CHUNK_SIZE", "1200"))
CHUNK_OVERLAP = int(os.getenv("TRACERAG_CHUNK_OVERLAP", "150"))


# ladybugdb schema (kùzu-compatible cypher ddl)
NODE_TABLE = "Entity"
REL_TABLE = "RELATES_TO"          # entity -> entity, same-window co-occurrence
DOC_TABLE = "Document"           # source doc node, no embedding
MENTIONS_TABLE = "MENTIONS"      # document -> entity
VECTOR_INDEX = "idx_entity_embedding"
VECTOR_METRIC = "cosine"
