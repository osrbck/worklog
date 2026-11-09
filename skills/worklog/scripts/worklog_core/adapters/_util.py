"""Helpers shared by adapters."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

PATCH_FILE = re.compile(r"\*\*\* (?:Update|Add|Delete) File: ([^\r\n\"\\]+)")
PATCH_MOVE = re.compile(r"\*\*\* Move to: ([^\r\n\"\\]+)")


def env_path(var: str) -> Optional[Path]:
    v = os.environ.get(var)
    return Path(v).expanduser() if v else None


def configured(cfg, name: str) -> Optional[Path]:
    p = (cfg.get("paths") or {}).get(name)
    return Path(p).expanduser() if p else None


def first_existing(*paths: Optional[Path]) -> Optional[Path]:
    for p in paths:
        if p and p.exists():
            return p
    return None


def modified_since(path: Path, start: datetime) -> bool:
    try:
        return path.stat().st_mtime >= start.timestamp()
    except OSError:
        return False


def iter_jsonl(path: Path, stats) -> Iterator[dict]:
    """Yield parsed records, skipping malformed lines instead of failing."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line or line[0] != "{":
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    stats["bad_lines"] = stats.get("bad_lines", 0) + 1
                    continue
                if isinstance(rec, dict):
                    yield rec
    except OSError as e:
        stats.setdefault("errors", []).append(f"{path.name}: {e}")


def read_json(path: Path, stats) -> Optional[dict]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError) as e:
        stats.setdefault("errors", []).append(f"{path.name}: {e}")
        return None


def patch_files(text: str):
    if not text or "*** " not in text:
        return []
    out = [m.strip() for m in PATCH_FILE.findall(text)]
    out += [m.strip() for m in PATCH_MOVE.findall(text)]
    return out
