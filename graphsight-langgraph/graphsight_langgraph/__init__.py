"""graphsight-langgraph: capture LangGraph runs as Graphsight traces.

    from graphsight_langgraph import LangGraphTracer, capture

    tracer = LangGraphTracer()
    result = graph.invoke(inputs, config={"callbacks": [tracer]})
    capture(tracer, query="...", answer=result.get("answer"))  # -> .graphsight/

Then browse every run: `graphsight .graphsight/`
"""
from .capture import capture, save_trace
from .episodes import Episode, EpisodeRetriever, recall
from .mapper import to_tracestate
from .schema import (
    SCHEMA_VERSION,
    AgentTrace,
    Retrieval,
    RetrievedItem,
    Span,
    TraceEdge,
)
from .tracer import LangGraphTracer

__all__ = [
    "SCHEMA_VERSION",
    "AgentTrace",
    "Episode",
    "EpisodeRetriever",
    "LangGraphTracer",
    "Retrieval",
    "RetrievedItem",
    "Span",
    "TraceEdge",
    "capture",
    "recall",
    "save_trace",
    "to_tracestate",
]
