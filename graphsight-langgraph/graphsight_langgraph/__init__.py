"""graphsight-langgraph — capture LangGraph runs as Graphsight traces.

    from graphsight_langgraph import LangGraphTracer, to_tracestate

    tracer = LangGraphTracer()
    result = graph.invoke(inputs, config={"callbacks": [tracer]})
    trace = tracer.finish(query="...", answer=result.get("answer"))
    studio_json = to_tracestate(trace)   # render in Graphsight Studio
"""
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
    "LangGraphTracer",
    "Retrieval",
    "RetrievedItem",
    "Span",
    "TraceEdge",
    "to_tracestate",
]
