"""Build the report or serve the generated static files for local review."""

import argparse
import functools
import http.server
from pathlib import Path

import httpx

from .analysis import compare
from .data import get_laps, load_race
from .report import build_report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    build = subcommands.add_parser(
        "build", help="Fetch or use cached results and generate the report"
    )
    build.add_argument("--config", type=Path, default=Path("race.toml"))
    build.add_argument("--data-dir", type=Path, default=Path("data"))
    build.add_argument("--output", type=Path, default=Path("site"))
    build.add_argument("--refresh", action="store_true", help="Refresh the saved source results")
    serve = subcommands.add_parser("serve", help="Serve the already generated report")
    serve.add_argument("--output", type=Path, default=Path("site"))
    serve.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.command == "build":
        try:
            race = load_race(args.config)
            laps = get_laps(race, args.data_dir, args.refresh)
            report = compare(race, laps)
            build_report(race, laps, report, args.output)
        except (ValueError, OSError, httpx.HTTPError) as error:
            parser.exit(1, f"Build failed: {error}\n")
        print(f"Built {args.output.resolve() / 'index.html'}")
        print(f"Validated {len(laps)} laps; finish margin {report['margin']} seconds.")
    else:
        if not (args.output / "index.html").exists():
            parser.exit(1, "Run `relay-race-analysis build` before serving the report.\n")
        handler = functools.partial(
            http.server.SimpleHTTPRequestHandler, directory=str(args.output.resolve())
        )
        with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
            print(f"Report: http://127.0.0.1:{args.port}", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
