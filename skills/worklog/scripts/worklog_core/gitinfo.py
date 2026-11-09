"""Git helpers: resolve project roots and list your commits in a time range (read-only)."""

from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from .timeparse import to_dt


@lru_cache(maxsize=None)
def find_root(path: str) -> Optional[str]:
    """Closest ancestor containing .git (dir or worktree file); None if not a repo or gone."""
    try:
        p = Path(path).expanduser().resolve()
    except (OSError, RuntimeError):
        return None
    for cand in (p, *p.parents):
        if (cand / ".git").exists():
            return str(cand)
    return None


def _git(root: str, *args: str, timeout: int = 15) -> Optional[str]:
    try:
        r = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


@lru_cache(maxsize=None)
def user_email(root: str) -> Optional[str]:
    out = _git(root, "config", "user.email")
    return out.strip().lower() if out and out.strip() else None


def commits(root: str, start, end, authors: List[str]) -> List[dict]:
    """Your non-merge commits on any branch in [start, end)."""
    emails = {a.lower() for a in authors} or ({user_email(root)} - {None})
    out = _git(root, "log", "--all", "--no-merges", f"--since={start.isoformat()}",
               f"--until={end.isoformat()}", "--date=iso-strict",
               "--format=%H%x1f%aI%x1f%ae%x1f%D%x1f%s", timeout=30)
    if not out:
        return []
    seen, result = set(), []
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) != 5:
            continue
        sha, when, email, refs, subject = parts
        if emails and email.lower() not in emails:
            continue
        if sha in seen:
            continue
        seen.add(sha)
        ts = to_dt(when)
        if ts is None or not (start <= ts < end):
            continue
        result.append({"sha": sha[:8], "time": ts.isoformat(timespec="minutes"),
                       "subject": subject.strip(), "refs": refs.strip() or None})
    result.sort(key=lambda c: c["time"])
    return result
