#!/usr/bin/env python3
"""worklog collector: read local AI coding sessions (read-only) and print a JSON digest.

Examples:
  worklog.py today
  worklog.py yesterday
  worklog.py 7d
  worklog.py this-week
  worklog.py 2026-11-01..2026-11-06
  worklog.py --since 2026-11-03T09:00 --until 2026-11-03T18:00 --project revora
  worklog.py --doctor            # show which sources were found
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from worklog_core import __version__, aggregate, config  # noqa: E402
from worklog_core.adapters import ADAPTERS  # noqa: E402
from worklog_core.timeparse import parse_range  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="worklog", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("range", nargs="?", default=None,
                    help="today | yesterday | this-week | last-week | this-month | last-month | "
                         "Nh | Nd | Nw | YYYY-MM-DD | A..B  (default: today)")
    ap.add_argument("--since", help="range start (date, datetime or relative)")
    ap.add_argument("--until", help="range end (date, datetime or relative)")
    ap.add_argument("--project", help="only projects whose path contains this text")
    ap.add_argument("--sources", help="comma separated subset, e.g. claude,codex")
    ap.add_argument("--idle", type=int, help="idle gap in minutes (default from config: 30)")
    ap.add_argument("--no-git", action="store_true", help="skip git commit lookup")
    ap.add_argument("--doctor", action="store_true", help="report detected sources and exit")
    ap.add_argument("--pretty", action="store_true", help="indent JSON output")
    ap.add_argument("--version", action="version", version=f"worklog {__version__}")
    args = ap.parse_args(argv)

    cfg = config.load()
    if args.idle:
        cfg["idle_minutes"] = args.idle
    wanted = [s.strip() for s in (args.sources.split(",") if args.sources else cfg["sources"]) if s.strip()]

    try:
        start, end = parse_range(args.range if not (args.since or args.until) else None,
                                 args.since, args.until)
    except ValueError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 2

    sources, sessions = [], []
    for name in wanted:
        mod = ADAPTERS.get(name)
        if mod is None:
            sources.append({"tool": name, "status": "unknown adapter"})
            continue
        root = mod.locate(cfg)
        info = {"tool": name, "label": mod.LABEL, "path": str(root) if root else None,
                "status": "found" if root else "not installed"}
        if root and not args.doctor:
            stats = {}
            try:
                found = [s for s in mod.collect(root, start, end, cfg, stats) if s.events]
            except Exception as e:  # an adapter bug must never break the whole report
                found = []
                stats.setdefault("errors", []).append(f"{type(e).__name__}: {e}")
            sessions.extend(found)
            info.update({"files_scanned": stats.get("files", 0), "sessions": len(found)})
            if stats.get("errors"):
                info["errors"] = stats["errors"][:5]
            if stats.get("bad_lines"):
                info["bad_lines"] = stats["bad_lines"]
        sources.append(info)

    if args.doctor:
        out = {"version": __version__, "config": str(config.config_path()), "sources": sources}
    else:
        out = aggregate.build(sessions, start, end, cfg, use_git=not args.no_git,
                              project_filter=args.project)
        out["sources"] = sources
        out["version"] = __version__
    if cfg.get("_config_error"):
        out["config_error"] = cfg["_config_error"]
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2 if args.pretty else None)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
