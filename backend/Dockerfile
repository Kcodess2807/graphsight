# TraceRAG backend — Hugging Face Spaces (Docker SDK), single warm instance.
FROM python:3.12-slim

# Build deps for any source-built wheels (as root).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential && \
    rm -rf /var/lib/apt/lists/*

# HF Spaces convention: run as uid 1000 with a writable home.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/home/user/.cache/huggingface \
    TRACERAG_DB_PATH=/home/user/app/graphs/fastapi__fastapi.lbug
WORKDIR /home/user/app

# Python deps first so this layer caches across code changes.
# Install CPU-only torch up front — otherwise sentence-transformers pulls the
# CUDA build (~1 GB of GPU libs) that's useless on CPU-only Spaces.
# Built from the repo root (docker-compose sets the context), so the engine package is visible.
COPY --chown=user backend/requirements.txt .
COPY --chown=user graphsight-memory /home/user/graphsight-memory
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir /home/user/graphsight-memory && \
    pip install --no-cache-dir -r requirements.txt

# Pre-pull the runtime models so the first request isn't a cold download:
# MiniLM embedder (ONNX) + spaCy small model. GLiNER is ingest-only, so it is skipped.
RUN python -m spacy download en_core_web_sm && \
    python -c "from graphsight_memory.embed import embedder; embedder('all-MiniLM-L6-v2')"

# App code + the baked-in, read-only demo graphs.
COPY --chown=user backend/ .

EXPOSE 7860
# One worker: the in-memory rate limiter + single-file LadybugDB require it.
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
