"""Stdlib static server for the bundled UI: SPA fallback to index.html,
/__trace__.json for a single trace file, /__runs__.json + /__run__/<name>
for a history directory."""
from __future__ import annotations

import json
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import unquote

DIST = Path(__file__).parent / "dist"
TRACE_ROUTE = "/__trace__.json"
RUNS_ROUTE = "/__runs__.json"
RUN_PREFIX = "/__run__/"
_MAX_RUNS = 200


class StudioHandler(SimpleHTTPRequestHandler):
    trace_path: Optional[Path] = None  # set by make_server
    history_dir: Optional[Path] = None

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        if path == TRACE_ROUTE:
            self._serve_file(self.trace_path, "No trace file was given to graphsight")
            return
        if path == RUNS_ROUTE:
            self._serve_runs()
            return
        if path.startswith(RUN_PREFIX):
            self._serve_run(unquote(path[len(RUN_PREFIX):]))
            return
        # SPA fallback: anything that isn't a real file gets index.html
        if not os.path.isfile(self.translate_path(path)):
            self.path = "/index.html"
        super().do_GET()

    def _send_json(self, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, path: Optional[Path], missing: str) -> None:
        if path is None or not path.is_file():
            self.send_error(404, missing)
            return
        self._send_json(path.read_bytes())

    def _serve_runs(self) -> None:
        if self.history_dir is None or not self.history_dir.is_dir():
            self.send_error(404, "No history directory was given to graphsight")
            return
        runs = []
        files = sorted(
            self.history_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:_MAX_RUNS]
        for f in files:
            entry = {"file": f.name}
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                entry["query"] = data.get("query")
                entry["computedAt"] = data.get("computedAt")
                entry["nodes"] = len((data.get("graph") or {}).get("nodes") or [])
            except (OSError, json.JSONDecodeError):
                continue  # skip unreadable files rather than break the list
            runs.append(entry)
        self._send_json(json.dumps(runs).encode("utf-8"))

    def _serve_run(self, name: str) -> None:
        # only bare filenames that exist in the dir, no traversal
        if (
            self.history_dir is None
            or Path(name).name != name
            or not name.endswith(".json")
        ):
            self.send_error(404, "Unknown run")
            return
        self._serve_file(self.history_dir / name, "Unknown run")

    def log_message(self, format: str, *args) -> None:  # keep the console quiet
        pass


def make_server(
    port: int,
    trace_path: Optional[Path] = None,
    history_dir: Optional[Path] = None,
) -> ThreadingHTTPServer:
    if not (DIST / "index.html").is_file():
        raise SystemExit(
            "Bundled UI missing (graphsight/dist/). This is a packaging "
            "error. Reinstall graphsight."
        )
    handler = partial(
        type(
            "BoundHandler",
            (StudioHandler,),
            {"trace_path": trace_path, "history_dir": history_dir},
        ),
        directory=str(DIST),
    )
    return ThreadingHTTPServer(("127.0.0.1", port), handler)
