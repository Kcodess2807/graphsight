"""Generate a tiny but REAL .lbug artifact for the end-to-end serve dry run.

Builds a 5-node / 4-edge graph (a PR that fixes a Bug in a Service, authored by a
Person, touching a Library) with real MiniLM embeddings + an HNSW index, then
publishes it into the mock S3 bucket exactly like the worker would. Returns the
metadata the control plane needs (s3_uri, checksum, size, entity_count).

Standalone:  python scripts/generate_dry_run_artifact.py
Programmatic: build_dry_run_artifact("org_test", 1) -> dict
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # backend/ on path

import storage
from tracerag import config
from tracerag.db import TraceDB

# 5 entities: (id, label, type)
NODES = [
    ("pr-42", "PR #42", "PR"),
    ("bug-7", "Bug #7", "Ticket"),
    ("paymentservice", "PaymentService", "Service"),
    ("authmodule", "auth module", "Library"),
    ("alice", "Alice", "Person"),
]

# 4 edges: (from, to, confidence)
EDGES = [
    ("pr-42", "bug-7", 0.95),           # PR #42 fixes Bug #7
    ("pr-42", "paymentservice", 0.90),  # PR #42 touches PaymentService
    ("bug-7", "paymentservice", 0.85),  # Bug #7 is in PaymentService
    ("alice", "pr-42", 0.80),           # Alice authored PR #42
]

# source docs (for citations): (doc_id, path, content, [mentioned entity ids])
DOCS = [
    ("pr-42#w0", "https://example.com/pr/42",
     "PR #42 by Alice fixes Bug #7: a null-pointer in the PaymentService refund "
     "path, also hardening the auth module token check.",
     ["pr-42", "bug-7", "paymentservice", "authmodule", "alice"]),
    ("bug-7#w0", "https://example.com/bug/7",
     "Bug #7: PaymentService crashes on refund when the auth module returns an "
     "expired token. Reported against the payments flow.",
     ["bug-7", "paymentservice", "authmodule"]),
]


def build_dry_run_artifact(org_id: str = "org_test", version: int = 1) -> dict:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(config.EMBED_MODEL)

    def embed(text: str) -> list[float]:
        vec = model.encode(text, normalize_embeddings=True)
        return [float(x) for x in vec]

    build_path = storage.build_dir(org_id) / f"dryrun_v{version}.lbug"
    if build_path.exists():
        # start clean so re-runs don't accumulate a stale schema/index
        import shutil
        shutil.rmtree(build_path, ignore_errors=True)

    db = TraceDB(build_path)
    db.init_schema()
    for nid, label, ntype in NODES:
        db.upsert_node(nid, label, ntype, embed(f"{label} {ntype}"))
    for a, b, conf in EDGES:
        db.add_relationship(a, b, conf)
    for doc_id, path, content, mentions in DOCS:
        db.upsert_document(doc_id, content=content, path=path)
        for eid in mentions:
            db.add_mention(doc_id, eid)
    db.build_vector_index()   # HNSW — required for vector_search at query time
    node_count = db.count_nodes()
    db.close()

    # publish into the mock bucket, exactly like the worker's upload step
    key = storage.artifact_key(org_id, version)
    s3_uri = storage.put_artifact(build_path, key)
    meta = {
        "org_id": org_id, "version": version, "s3_uri": s3_uri,
        "checksum_sha256": storage.sha256_file(build_path),
        "size_bytes": build_path.stat().st_size,
        "entity_count": node_count,
        "bucket_path": str(storage.S3_MOCK_DIR / key),
    }
    return meta


if __name__ == "__main__":
    import json

    info = build_dry_run_artifact()
    print(json.dumps(info, indent=2))
    print(f"\nArtifact published to mock bucket: {info['bucket_path']}")
