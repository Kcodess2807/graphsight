"""Map an AgentTrace onto the Studio's TraceState (frontend/src/types/trace.ts).
Positions are {0,0} on purpose; the Studio re-layouts client-side."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from .schema import AgentTrace

# free-form kinds -> the Studio's entity types
_KIND_TO_ENTITY = {
    "pr": "PR",
    "pull_request": "PR",
    "pullrequest": "PR",
    "service": "Service",
    "person": "Person",
    "user": "Person",
    "author": "Person",
    "document": "Document",
    "doc": "Document",
    "chunk": "Document",
    "repo": "Repo",
    "repository": "Repo",
    "branch": "Repo",
    "library": "Library",
    "package": "Library",
    "ticket": "Ticket",
    "issue": "Ticket",
    "jira": "Ticket",
    "team": "Team",
    "tool": "Tool",
}

_MAX_CONTEXT_CHARS = 8000


def to_tracestate(trace: AgentTrace) -> dict[str, Any]:
    """Return a TraceState-shaped dict ready for the Studio."""
    has_edges = any(r.edges for r in trace.retrievals)

    # nodes
    nodes: list[dict[str, Any]] = []
    seen_nodes: set[str] = set()
    for retrieval in trace.retrievals:
        for item in retrieval.items:
            if item.id in seen_nodes:
                continue
            seen_nodes.add(item.id)
            nodes.append(
                {
                    "id": item.id,
                    "label": item.label,
                    "type": _KIND_TO_ENTITY.get(item.kind.lower().strip(), "Document"),
                    "active": True,  # everything retrieved was selected
                    "position": {"x": 0, "y": 0},  # Studio re-layouts with dagre
                    "similarity": item.vector_score,
                    "score": item.score,
                    "meta": {
                        "subtitle": f"via {trace.framework} · {retrieval.arm} arm",
                        "snippet": (item.content or "")[:600] or None,
                        "scoreGraph": item.graph_score,
                        "sourceUrl": item.source_uri,
                    },
                }
            )

    # edges (only between retrieved nodes)
    edges: list[dict[str, Any]] = []
    for retrieval in trace.retrievals:
        for i, edge in enumerate(retrieval.edges):
            if edge.source not in seen_nodes or edge.target not in seen_nodes:
                continue
            edges.append(
                {
                    "id": f"e_{retrieval.span_id[:8]}_{i}",
                    "source": edge.source,
                    "target": edge.target,
                    "confidence": edge.weight if edge.weight is not None else 0.7,
                    "active": True,
                    "relation": edge.relation,
                }
            )

    # execution steps from spans
    ordered = sorted(trace.spans, key=lambda s: s.start_ms)
    steps = []
    for index, span in enumerate(ordered):
        duration = (span.end_ms - span.start_ms) if span.end_ms is not None else None
        step = {
            "id": span.id,
            "index": index,
            "title": span.name,
            "detail": f"{span.kind} · {span.status}",
            "status": "complete" if span.status == "ok" else "pending",
            "badge": span.kind,
            "durationMs": round(duration, 1) if duration is not None else None,
        }
        if span.kind == "retriever":
            arm = next((r.arm for r in trace.retrievals if r.span_id == span.id), None)
            if arm in ("vector", "graph"):
                step["arm"] = arm
        steps.append(step)

    # context for downstream answer generation
    context = "\n\n".join(
        item.content for r in trace.retrievals for item in r.items if item.content
    )[:_MAX_CONTEXT_CHARS] or None

    scores = [item.score for r in trace.retrievals for item in r.items if item.score is not None]

    return {
        "id": f"trace_lg_{int(time.time() * 1000)}",
        "query": trace.query,
        "computedAt": datetime.now(timezone.utc).isoformat(),
        "weights": {
            # honest split: this router didn't run, so weights describe the
            # observed arms, not a fusion decision
            "vector": 0.5 if has_edges else 1.0,
            "graph": 0.5 if has_edges else 0.0,
            "intent": "relational" if has_edges else "conceptual",
        },
        "confidence": {
            "score": round(sum(scores) / len(scores), 3) if scores else 0.0,
            "uncertainty": 0.0,
            "rationale": (
                f"External {trace.framework} trace — scores reported by the "
                "retriever; Graphsight does not recompute them."
            ),
        },
        "steps": steps,
        "metrics": {
            "queryTimeSec": round((trace.latency_ms or 0.0) / 1000.0, 3),
            "nodesEvaluated": len(nodes),
        },
        "graph": {"nodes": nodes, "edges": edges},
        "context": context,
    }
