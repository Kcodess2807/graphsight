"""Viewer server tests: trace route, history routes, traversal guard, SPA fallback."""
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from graphsight.server import make_server


@pytest.fixture
def history(tmp_path):
    hist = tmp_path / "runs"
    hist.mkdir()
    for name, query in [("a.json", "first run"), ("b.json", "second run")]:
        (hist / name).write_text(
            json.dumps({"query": query, "computedAt": "2026-07-26T00:00:00Z",
                        "graph": {"nodes": [], "edges": []}}),
            encoding="utf-8",
        )
    (hist / "broken.json").write_text("{not json", encoding="utf-8")
    return hist


@pytest.fixture
def serve(history, tmp_path):
    trace = tmp_path / "single.json"
    trace.write_text(json.dumps({"query": "solo"}), encoding="utf-8")
    server = make_server(0, trace_path=trace, history_dir=history)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


def get(url):
    with urllib.request.urlopen(url, timeout=5) as resp:
        return resp.status, resp.read()


def test_trace_route(serve):
    status, body = get(f"{serve}/__trace__.json")
    assert status == 200
    assert json.loads(body)["query"] == "solo"


def test_runs_index_skips_broken_files(serve):
    status, body = get(f"{serve}/__runs__.json")
    assert status == 200
    runs = json.loads(body)
    assert {r["file"] for r in runs} == {"a.json", "b.json"}  # broken.json skipped
    assert all("query" in r for r in runs)


def test_run_fetch(serve):
    status, body = get(f"{serve}/__run__/a.json")
    assert status == 200
    assert json.loads(body)["query"] == "first run"


@pytest.mark.parametrize("path", [
    "/__run__/..%2f..%2fsecrets.txt",
    "/__run__/../a.json",
    "/__run__/a.txt",
    "/__run__/missing.json",
])
def test_run_traversal_and_unknowns_404(serve, path):
    with pytest.raises(urllib.error.HTTPError) as err:
        get(f"{serve}{path}")
    assert err.value.code == 404


def test_spa_fallback_serves_index(serve):
    status, body = get(f"{serve}/memory/import")
    assert status == 200
    assert b"<!doctype html" in body.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
