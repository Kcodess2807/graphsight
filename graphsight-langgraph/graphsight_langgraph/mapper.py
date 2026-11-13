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
    "commit": "Commit",
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
    # retrieved vs used: only meaningful when an answer + overlaps exist
    has_usage = trace.answer is not None and any(
        item.answer_overlap is not None for r in trace.retrievals for item in r.items
    )
    _USED = 0.2  # lexical-overlap threshold for "surfaced in the answer"

    # nodes
    nodes: list[dict[str, Any]] = []
    seen_nodes: set[str] = set()
    used_ids: set[str] = set()
    for retrieval in trace.retrievals:
        for item in retrieval.items:
            if item.id in seen_nodes:
                continue
            seen_nodes.add(item.id)
            if has_usage:
                used = (item.answer_overlap or 0.0) >= _USED
                # say what was measured, not what it implies. a chunk used as a
                # negative constraint leaves no lexical trace but is load bearing.
                subtitle = (
                    f"overlaps the answer · via {trace.framework}"
                    if used
                    else f"no lexical trace in answer · via {trace.framework}"
                )
            else:
                used = True  # no answer to compare against, show everything plain
                subtitle = f"via {trace.framework} · {retrieval.arm} arm"
            if used:
                used_ids.add(item.id)
            nodes.append(
                {
                    "id": item.id,
                    "label": item.label,
                    "type": _KIND_TO_ENTITY.get(item.kind.lower().strip(), "Document"),
                    "active": used,  # unused retrievals render dimmed
                    "position": {"x": 0, "y": 0},  # Studio re-layouts with dagre
                    "similarity": item.vector_score,
                    "score": item.score,
                    "meta": {
                        "subtitle": subtitle,
                        "snippet": (item.content or "")[:600] or None,
                        "scoreGraph": item.graph_score,
                        "sourceUrl": item.source_uri,
                        "answerOverlap": item.answer_overlap,
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
                    "active": edge.source in used_ids and edge.target in used_ids,
                    "relation": edge.relation,
                }
            )

    # context for downstream answer generation
    context = "\n\n".join(
        item.content for r in trace.retrievals for item in r.items if item.content
    )[:_MAX_CONTEXT_CHARS] or None

    return {
        "id": f"trace_lg_{int(time.time() * 1000)}",
        "query": trace.query,
        "answer": trace.answer,
        "outcome": trace.outcome,
        "computedAt": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "queryTimeSec": round((trace.latency_ms or 0.0) / 1000.0, 3),
        },
        "graph": {"nodes": nodes, "edges": edges},
        "context": context,
    }
