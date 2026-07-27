"""History capture tests."""
import json

import pytest

from graphsight_langgraph import AgentTrace, save_trace
from graphsight_langgraph.capture import _slug


def test_slug():
    assert _slug("Why is checkout failing?!") == "why-is-checkout-failing"
    assert _slug("") == "run"
    assert len(_slug("x" * 100)) == 40


def test_save_trace_writes_viewer_json(tmp_path):
    path = save_trace(AgentTrace(query="who broke auth?"), dir=tmp_path)
    assert path.parent == tmp_path
    assert path.name.endswith("_who-broke-auth.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["query"] == "who broke auth?"
    assert "graph" in data  # viewer format, not the raw AgentTrace


def test_env_dir_override(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHSIGHT_DIR", str(tmp_path / "custom"))
    path = save_trace(AgentTrace(query="q"))
    assert path.parent == tmp_path / "custom"


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
