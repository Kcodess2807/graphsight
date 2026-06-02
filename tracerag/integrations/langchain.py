"""Drop-in LangChain BaseRetriever backed by the TraceRouter.

    retriever = TraceRAGRetriever.from_db(db)
    docs = retriever.invoke("which PR caused the payment outage?")
"""

from __future__ import annotations

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from .. import config
from ..db import TraceDB
from ..router import RoutedNode, TraceRouter


def format_page_content(node: RoutedNode) -> str:
    """Entity line + the raw chunk text mentioning it (deduped, capped).

    Shared by the retriever and the benchmark so both measure the exact same
    LLM-facing context.
    """
    content = f"Entity: {node.label or node.id} ({node.type or 'Unknown'})"
    snippets, seen = [], set()
    for d in node.documents:
        text = (d.get("content") or "").strip()
        if text and text not in seen:
            seen.add(text)
            snippets.append(text)
        if len(snippets) >= config.RETRIEVAL_SNIPPETS_PER_NODE:
            break
    if snippets:
        content += "\n\nContext:\n" + "\n---\n".join(snippets)
    return content


class TraceRAGRetriever(BaseRetriever):
    """Wraps TraceRouter so any LangChain chain can retrieve from the .lbug graph."""

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
        for node in response.results:
            docs.append(Document(
                page_content=format_page_content(node),
                metadata={
                    "id": node.id,
                    "score_total": node.score_total,
                    "score_vector": node.score_vector,
                    "score_graph": node.score_graph,
                    "trace_log": response.trace_log,
                },
            ))
        return docs
