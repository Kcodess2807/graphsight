"""Worker configuration (env-driven). Kept separate from tracerag/config.py so
the serving path and the compile path have independent config surfaces."""

import os

# --- Broker / result backend (Redis) ---
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)

# --- Debounce-and-coalesce window ---
# Hold a reconcile for DEBOUNCE_WINDOW seconds; every new webhook slides the
# deadline forward so a burst of PRs collapses into ONE compile. DEBOUNCE_MAX_WAIT
# caps the slide so a continuously-active org still compiles eventually.
DEBOUNCE_WINDOW = int(os.getenv("TRACERAG_DEBOUNCE_WINDOW", "120"))        # 2 min
DEBOUNCE_MAX_WAIT = int(os.getenv("TRACERAG_DEBOUNCE_MAX_WAIT", "600"))    # 10 min cap
# How often Celery Beat sweeps for windows that have closed.
SWEEP_INTERVAL = int(os.getenv("TRACERAG_SWEEP_INTERVAL", "30"))           # seconds

# --- Per-org compile lock: serialize compiles for one org without serializing
# the cheap incremental-compute step. TTL is a safety release if a worker dies
# mid-compile. ---
COMPILE_LOCK_TTL = int(os.getenv("TRACERAG_COMPILE_LOCK_TTL", "1800"))     # 30 min

# --- Artifact storage (S3) — consumed by the compile/upload stage (TODO). ---
ARTIFACT_S3_BUCKET = os.getenv("TRACERAG_ARTIFACT_S3_BUCKET", "")
ARTIFACT_S3_PREFIX = os.getenv("TRACERAG_ARTIFACT_S3_PREFIX", "artifacts")
