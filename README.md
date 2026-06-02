# 🕸️ TraceRAG: The Observable GraphRAG Engine

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![LadybugDB](https://img.shields.io/badge/Powered_by-LadybugDB-red.svg)](https://github.com/ladybugdb/ladybug)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**TraceRAG** is a local-first, headless GraphRAG curation and debugging layer built natively on **LadybugDB**. 

It eliminates the 'dual-database sync hell' by combining native vector indexes + graph storage in a single .lbug file. TraceRAG provides human-in-the-loop entity curation, visual query tracing, and drop-in LangChain compatibility to make agent memory reliable in production.

---

## 🛑 The Core Problem: Why GraphRAG Fails in Production

Building multi-hop reasoning for AI agents is currently broken due to three infrastructural bottlenecks:

1. **Dual-Store Sync Hell:** Running a dedicated Graph DB (like Neo4j) alongside a Vector DB (like Pinecone) requires complex ETL pipelines, fragile ID-mapping, and constant synchronization. Partial ingest failures leave the memory corrupted.
2. **The "Graph Janitor" Problem:** LLM-based auto-extraction on noisy datasets creates massive entity drift (e.g., extracting `PaymentService`, `payments-v2`, and `pay_svc` as separate nodes). Manual curation scales horribly.
3. **Black-Box Routing:** When a hybrid retriever hallucinates, developers have no observability into *why* the router prioritized a specific graph edge over a semantic vector chunk. 

## 💡 The Solution: TraceRAG Architecture

TraceRAG is not a new database. It is an orchestration and observability layer built on **LadybugDB** (the embedded, single-file successor to Kùzu), leveraging its native support for nested vector and graph data types.

### Key Features
* **Zero-Sync Storage (100% Native LadybugDB):** Vectors and graphs live in the same schema. One database, one file (`.lbug`), zero sync hell.
* **Two-Tier Smart Curation:** 
  * *Fast Mode (Recall):* Ingestion automatically stages high-confidence duplicate nodes using pure vector cosine similarity (`>0.92`).
  * *Deep Merge (Precision):* A lightweight local LLM (e.g., Llama-3 via Ollama) is only triggered for "grey-zone" entities (e.g., `0.85–0.92` similarity), reducing compute overhead while preventing hallucinated merges.
* **Visual Query Tracer:** A Cytoscape.js UI that visually maps the router's execution plan, showing exactly which semantic chunks were retrieved and which graph edges were traversed.
* **Headless-First & CI-Ready:** Designed to run via CLI in deployment pipelines, with the UI completely decoupled.
* **Dynamic Schema Inference:** Automatically generates `CREATE NODE TABLE` and `CREATE REL TABLE` schemas during the first extraction run.
* Drop-in LangChain BaseRetriever + LlamaIndex compatibility (one-line swap).

---
