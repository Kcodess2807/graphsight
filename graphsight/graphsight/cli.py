"""graphsight CLI: open a trace (or a whole run history) in the bundled UI."""
from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path
from typing import Optional

from .server import RUNS_ROUTE, TRACE_ROUTE, make_server


def main(argv: Optional[list[str]] = None) -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, OSError):
            pass

    parser = argparse.ArgumentParser(
        prog="graphsight",
        description="Open a trace_state.json, or a history directory like .graphsight/, in your browser.",
    )
    parser.add_argument("trace", nargs="?", type=Path,
                        help="a trace_state.json, or a directory of them (e.g. .graphsight/); "
                             "omit to open the import page")
    parser.add_argument("--port", type=int, default=4630, help="port to serve on (default 4630)")
    parser.add_argument("--no-browser", action="store_true", help="don't open the browser")
    args = parser.parse_args(argv)

    trace_path: Optional[Path] = None
    history_dir: Optional[Path] = None
    if args.trace is not None:
        target = args.trace.resolve()
        if target.is_dir():
            history_dir = target
        elif target.is_file():
            trace_path = target
        else:
            parser.error(f"not found: {target}")

    server = make_server(args.port, trace_path=trace_path, history_dir=history_dir)
    url = f"http://127.0.0.1:{args.port}/memory/import"
    if trace_path is not None:
        url += f"?src={TRACE_ROUTE}"
    elif history_dir is not None:
        url += f"?runs={RUNS_ROUTE}"

    print(f"graphsight serving at {url}")
    if trace_path is not None:
        print(f"trace: {trace_path}")
    if history_dir is not None:
        print(f"history: {history_dir}")
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
