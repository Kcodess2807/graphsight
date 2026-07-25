"""Local run history: save every finished trace, browse them all later
with `graphsight .graphsight/`."""
from __future__ import annotations

import json
import re
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

from .mapper import to_tracestate
from .schema import AgentTrace

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str, limit: int = 40) -> str:
    return _SLUG_RE.sub("-", text.lower()).strip("-")[:limit] or "run"


def save_trace(trace: AgentTrace, dir: Union[str, Path, None] = None) -> Path:
    """Write the trace to the history dir; returns the file path.

    Default dir is $GRAPHSIGHT_DIR or ./.graphsight. Files are
    <utc-timestamp>_<query-slug>.json in the viewer's TraceState format.
    """
    target = Path(dir or os.environ.get("GRAPHSIGHT_DIR") or ".graphsight")
    target.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    path = target / f"{stamp}_{_slug(trace.query)}.json"
    path.write_text(json.dumps(to_tracestate(trace), indent=2), encoding="utf-8")
    return path


def capture(
    tracer,
    query: Optional[str] = None,
    answer: Optional[str] = None,
    dir: Union[str, Path, None] = None,
) -> Path:
    """finish() + save_trace() in one call."""
    return save_trace(tracer.finish(query=query, answer=answer), dir=dir)
