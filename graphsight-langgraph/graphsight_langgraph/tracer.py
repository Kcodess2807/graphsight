"""Callback handler that captures a LangGraph run as an AgentTrace.

Pass it via config={"callbacks": [tracer]}, then call tracer.finish().
Remember to pass the node's config into sub-runnables or their events
won't reach the tracer (see README).
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, Optional
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.documents import Document

from .schema import AgentTrace, Retrieval, RetrievedItem, Span, TraceEdge

_SCORE_KEYS = ("score", "relevance_score", "similarity", "_score", "vector_score")
# LangGraph internals that fire chain events but aren't user nodes
_NOISE_NAMES = {"LangGraph", "RunnableSequence", "RunnableCallable", "ChannelWrite", "__start__", "__end__"}


def _doc_id(doc: Document) -> str:
    for key in ("id", "node_id", "doc_id"):
        if doc.metadata.get(key):
            return str(doc.metadata[key])
    if getattr(doc, "id", None):
        return str(doc.id)
    return "doc_" + hashlib.sha1(doc.page_content.encode("utf-8")).hexdigest()[:10]


def _doc_score(doc: Document) -> Optional[float]:
    for key in _SCORE_KEYS:
        value = doc.metadata.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


class LangGraphTracer(BaseCallbackHandler):
    """Collects spans + retrievals from a LangGraph (or any LangChain) run."""

    def __init__(self) -> None:
        super().__init__()
        self._t0 = time.monotonic()
        self._spans: dict[str, Span] = {}
        self._order: list[str] = []
        self._retrievals: list[Retrieval] = []
        self._first_query: Optional[str] = None

    # span bookkeeping
    def _now_ms(self) -> float:
        return (time.monotonic() - self._t0) * 1000.0

    def _open_span(
        self,
        run_id: UUID,
        parent_run_id: Optional[UUID],
        name: str,
        kind: str,
    ) -> Span:
        span = Span(
            id=str(run_id),
            name=name,
            kind=kind,  # type: ignore[arg-type]
            parent_id=str(parent_run_id) if parent_run_id else None,
            start_ms=self._now_ms(),
        )
        self._spans[span.id] = span
        self._order.append(span.id)
        return span

    def _close_span(self, run_id: UUID, status: str = "ok") -> None:
        span = self._spans.get(str(run_id))
        if span is not None:
            span.end_ms = self._now_ms()
            span.status = status  # type: ignore[assignment]

    @staticmethod
    def _resolve_name(
        serialized: Optional[dict[str, Any]],
        metadata: Optional[dict[str, Any]],
        kwargs: dict[str, Any],
        fallback: str,
    ) -> str:
        return (
            kwargs.get("name")
            or (serialized or {}).get("name")
            or (metadata or {}).get("langgraph_node")
            or fallback
        )

    # chain events -> node spans
    def on_chain_start(
        self,
        serialized: Optional[dict[str, Any]],
        inputs: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        name = self._resolve_name(serialized, metadata, kwargs, "chain")
        node = (metadata or {}).get("langgraph_node")
        # keep exactly one span per user node execution; skip framework noise
        if name in _NOISE_NAMES or node is None or name != node:
            return
        self._open_span(run_id, parent_run_id, name, "node")

    def on_chain_end(self, outputs: Any, *, run_id: UUID, **kwargs: Any) -> None:
        self._close_span(run_id)

    def on_chain_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._close_span(run_id, status="error")

    # retriever events -> spans + retrievals
    def on_retriever_start(
        self,
        serialized: Optional[dict[str, Any]],
        query: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        if self._first_query is None:
            self._first_query = query
        name = self._resolve_name(serialized, metadata, kwargs, "retriever")
        span = self._open_span(run_id, parent_run_id, name, "retriever")
        self._retrievals.append(Retrieval(span_id=span.id, query=query))

    def on_retriever_end(
        self, documents: list[Document], *, run_id: UUID, **kwargs: Any
    ) -> None:
        self._close_span(run_id)
        retrieval = next(
            (r for r in reversed(self._retrievals) if r.span_id == str(run_id)), None
        )
        if retrieval is None:
            return
        seen_edges: set[tuple[str, str, str]] = set()
        for doc in documents:
            item_id = _doc_id(doc)
            retrieval.items.append(
                RetrievedItem(
                    id=item_id,
                    label=str(doc.metadata.get("label") or doc.metadata.get("title") or item_id),
                    kind=str(doc.metadata.get("kind") or doc.metadata.get("type") or "document"),
                    score=_doc_score(doc),
                    vector_score=_doc_score(doc),
                    content=doc.page_content,
                    source_uri=doc.metadata.get("source") or doc.metadata.get("source_uri"),
                    metadata={
                        k: v
                        for k, v in doc.metadata.items()
                        if k not in ("edges",) and isinstance(v, (str, int, float, bool))
                    },
                )
            )
            # optional relational structure carried on the document
            for edge in doc.metadata.get("edges") or []:
                key = (str(edge.get("source")), str(edge.get("target")), str(edge.get("relation")))
                if key in seen_edges or not edge.get("source") or not edge.get("target"):
                    continue
                seen_edges.add(key)
                retrieval.edges.append(
                    TraceEdge(
                        source=str(edge["source"]),
                        target=str(edge["target"]),
                        relation=edge.get("relation"),
                        weight=edge.get("weight"),
                    )
                )
        retrieval.arm = "graph" if retrieval.edges else "vector"

    def on_retriever_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._close_span(run_id, status="error")

    # llm / tool events -> plain spans
    def on_llm_start(
        self,
        serialized: Optional[dict[str, Any]],
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        self._open_span(
            run_id, parent_run_id, self._resolve_name(serialized, metadata, kwargs, "llm"), "llm"
        )

    def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
        self._close_span(run_id)

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._close_span(run_id, status="error")

    def on_tool_start(
        self,
        serialized: Optional[dict[str, Any]],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        self._open_span(
            run_id, parent_run_id, self._resolve_name(serialized, metadata, kwargs, "tool"), "tool"
        )

    def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        self._close_span(run_id)

    def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._close_span(run_id, status="error")

    # result
    def finish(self, query: Optional[str] = None, answer: Optional[str] = None) -> AgentTrace:
        """Assemble the AgentTrace after the run completes."""
        spans = [self._spans[sid] for sid in self._order]
        for span in spans:  # close anything left dangling
            if span.end_ms is None:
                span.end_ms = self._now_ms()
                span.status = "ok" if span.status == "running" else span.status
        latency = max((s.end_ms or 0.0) for s in spans) if spans else None
        return AgentTrace(
            query=query or self._first_query or "",
            spans=spans,
            retrievals=self._retrievals,
            answer=answer,
            latency_ms=latency,
        )
