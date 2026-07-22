---
title: TraceRAG API
emoji: 🐞
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# TraceRAG — Backend API

GraphRAG retrieval engine (FastAPI + LadybugDB). This Space serves the backend
for the [TraceRAG Studio](https://github.com/Kcodess2807/graphsight) frontend.

Runs as a single warm container (Docker SDK). The demo graphs are baked into the
image; secrets (LLM keys, Postgres URL, Clerk) are supplied via Space **Settings → Secrets**.

See `../DEPLOY.md` in the repo for the full deployment guide.
