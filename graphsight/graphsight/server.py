"""Stdlib static server for the bundled UI: SPA fallback to index.html,
plus /__trace__.json serving the trace file given on the command line."""
from __future__ import annotations

import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

DIST = Path(__file__).parent / "dist"
TRACE_ROUTE = "/__trace__.json"


class StudioHandler(SimpleHTTPRequestHandler):
    trace_path: Optional[Path] = None  # set by make_server

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        if path == TRACE_ROUTE:
            self._serve_trace()
            return
        # SPA fallback: anything that isn't a real file gets index.html
        if not os.path.isfile(self.translate_path(path)):
            self.path = "/index.html"
        super().do_GET()

    def _serve_trace(self) -> None:
        if self.trace_path is None or not self.trace_path.is_file():
            self.send_error(404, "No trace file was given to graphsight")
            return
        body = self.trace_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # keep the console quiet
        pass


def make_server(port: int, trace_path: Optional[Path]) -> ThreadingHTTPServer:
    if not (DIST / "index.html").is_file():
        raise SystemExit(
            "Bundled UI missing (graphsight/dist/). This is a packaging "
            "error — reinstall graphsight."
        )
    handler = partial(
        type("BoundHandler", (StudioHandler,), {"trace_path": trace_path}),
        directory=str(DIST),
    )
    return ThreadingHTTPServer(("127.0.0.1", port), handler)
