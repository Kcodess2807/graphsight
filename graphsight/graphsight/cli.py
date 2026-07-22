"""graphsight CLI — open a trace in the bundled Studio UI."""
from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path
from typing import Optional

from .server import TRACE_ROUTE, make_server


def main(argv: Optional[list[str]] = None) -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, OSError):
            pass

    parser = argparse.ArgumentParser(
        prog="graphsight",
        description="Serve the Graphsight Studio locally and open a trace_state.json in it.",
    )
    parser.add_argument("trace", nargs="?", type=Path,
                        help="path to a trace_state.json (optional — omit to open the import page)")
    parser.add_argument("--port", type=int, default=4630, help="port to serve on (default 4630)")
    parser.add_argument("--no-browser", action="store_true", help="don't open the browser")
    args = parser.parse_args(argv)

    trace_path = args.trace.resolve() if args.trace else None
    if trace_path is not None and not trace_path.is_file():
        parser.error(f"trace file not found: {trace_path}")

    server = make_server(args.port, trace_path)
    url = f"http://127.0.0.1:{args.port}/memory/import"
    if trace_path is not None:
        url += f"?src={TRACE_ROUTE}"

    print(f"graphsight serving at {url}")
    if trace_path is not None:
        print(f"trace: {trace_path}")
    print("Ctrl+C to stop")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
