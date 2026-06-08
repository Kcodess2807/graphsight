"""LangChain BaseRetriever backed by the TraceRouter."""

from __future__ import annotations

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from .. import config
from ..db import TraceDB
from ..router import RoutedNode, TraceRouter


def format_page_content(node: RoutedNode, seen_chunk_ids: set[str] | None = None) -> str:
    """Entity line + its chunk text, globally deduped by chunk id."""
    seen = seen_chunk_ids if seen_chunk_ids is not None else set()
    label, ntype = node.label or node.id, node.type or "Unknown"
    content = f"Entity: {label} ({ntype})"
    parts: list[str] = []
    for d in node.documents:
        cid = d.get("doc_id")
        text = (d.get("content") or "").strip()
        if not text:
            continue
        if cid not in seen:
            seen.add(cid)
            parts.append(text)
        else:
            parts.append(f"[Trace: {label} ({ntype}) -> {cid}]")
    if parts:
        content += "\n\nContext:\n" + "\n---\n".join(parts)
    return content


class TraceRAGRetriever(BaseRetriever):
    """Retriever that wraps TraceRouter over the .lbug graph."""

    model_config = {"arbitrary_types_allowed": True}

    router: TraceRouter
    k: int = config.TOP_K_VECTOR

    @classmethod
    def from_db(cls, db: TraceDB, k: int = config.TOP_K_VECTOR) -> "TraceRAGRetriever":
        return cls(router=TraceRouter(db), k=k)

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        response = self.router.route(query, top_k=self.k)
        docs: list[Document] = []
        seen_chunk_ids: set[str] = set()
        for node in response.results:
            docs.append(Document(
                page_content=format_page_content(node, seen_chunk_ids),
                metadata={
                    "id": node.id,
                    "score_total": node.score_total,
                    "score_vector": node.score_vector,
                    "score_graph": node.score_graph,
                    "trace_log": response.trace_log,
                },
            ))
        return docs
