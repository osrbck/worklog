"""Turn raw sessions into a compact, project-grouped report the model can summarize."""

from __future__ import annotations

import fnmatch
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional

from . import gitinfo
from .config import NOTABLE_COMMAND
from .model import Session
from .redact import clean_prompt, redact

_NOTABLE = re.compile(NOTABLE_COMMAND)


def active_minutes(events: List[datetime], idle: int, burst: int) -> int:
    """Sum of gaps between consecutive events that are <= idle; each burst gets `burst` minutes."""
    if not events:
        return 0
    ev = sorted(events)
    total = timedelta()
    gap = timedelta(minutes=idle)
    bursts = 1
    for a, b in zip(ev, ev[1:]):
        d = b - a
        if d <= gap:
            total += d
        else:
            bursts += 1
    return int(round(total.total_seconds() / 60)) + bursts * burst if total or bursts else 0


def per_day(events: List[datetime], idle: int, burst: int) -> Dict[str, int]:
    days = defaultdict(list)
    for e in events:
        days[e.date().isoformat()].append(e)
    return {d: active_minutes(v, idle, burst) for d, v in sorted(days.items())}


def _merge_subagents(sessions: List[Session]) -> List[Session]:
    """Fold subagent/workflow threads into their root session.

    When the root itself has no activity in range, siblings are folded into the first sibling.
    """
    by_key = {(s.tool, s.session_id): s for s in sessions}
    anchors: Dict[tuple, Session] = {}
    out = []
    for s in sorted(sessions, key=lambda x: x.start):
        if not s.parent_id:
            out.append(s)
            continue
        key = (s.tool, s.parent_id)
        parent = by_key.get(key) or anchors.get(key)
        if parent is None or parent is s:
            anchors[key] = s
            s.title = s.title or s.agent
            s.add_subtask(s.agent)
            out.append(s)
            continue
        parent.events.extend(s.events)
        for f in s.files:
            parent.add_file(f)
        for c in s.commands:
            parent.add_command(c)
        parent.add_subtask(s.agent)
        parent.subagents += 1
        if not parent.last_reply and s.last_reply:
            parent.last_reply = s.last_reply
    return out


def _rel(path: str, root: Optional[str], cwd: Optional[str]) -> str:
    if not path:
        return path
    p = path
    if not os.path.isabs(p) and cwd:
        p = os.path.normpath(os.path.join(cwd, p))
    if root and (p == root or p.startswith(root.rstrip(os.sep) + os.sep)):
        return os.path.relpath(p, root)
    home = os.path.expanduser("~")
    return "~" + p[len(home):] if p.startswith(home + os.sep) else p


_SCRATCH = ("/tmp/", "/var/folders/", "/private/tmp/", "/dev/")


def _scratch(path: str, root: Optional[str], cwd: Optional[str]) -> bool:
    """Temp files outside the project (e.g. /tmp/helper.mjs) aren't project work."""
    if not path:
        return True
    for base in (root, cwd):
        if base and (path == base or path.startswith(base.rstrip(os.sep) + os.sep)):
            return False
    return any(path.startswith(p) for p in _SCRATCH)


def _excluded(root: str, name: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(root, pat) or fnmatch.fnmatch(name, pat) for pat in patterns)


def _issue_keys(texts: Iterable[str], pattern: str, deny: Iterable[str]) -> List[str]:
    rx = re.compile(pattern)
    deny = {d.upper() for d in deny}
    c = Counter()
    for t in texts:
        for k in rx.findall(t or ""):
            if k.split("-")[0].upper() not in deny:
                c[k] += 1
    return [k for k, _ in c.most_common(20)]


def build(sessions: Iterable[Session], start, end, cfg, *, use_git: bool = True,
          project_filter: Optional[str] = None) -> dict:
    idle, burst = cfg["idle_minutes"], cfg["min_burst_minutes"]
    sessions = _merge_subagents([s for s in sessions if s.events])
    sessions = [s for s in sessions if s.has_work()]

    groups: Dict[str, List[Session]] = defaultdict(list)
    for s in sessions:
        root = (gitinfo.find_root(s.cwd) if s.cwd else None) or s.cwd or "(unknown)"
        groups[root].append(s)

    projects, all_events = [], []
    for root, items in groups.items():
        name = os.path.basename(root.rstrip(os.sep)) or root
        if _excluded(root, name, cfg["exclude_projects"]):
            continue
        if project_filter and project_filter.lower() not in root.lower():
            continue
        is_git = gitinfo.find_root(root) == root if root != "(unknown)" else False
        events = [e for s in items for e in s.events]
        all_events.extend(events)
        commits = gitinfo.commits(root, start, end, cfg["git_authors"]) if (use_git and is_git) else []

        out_sessions = []
        for s in sorted(items, key=lambda x: x.start):
            files = [_rel(f, root if is_git else None, s.cwd) for f in s.files if not _scratch(f, root, s.cwd)]
            notable = [redact(c)[:200] for c in s.commands
                       if _NOTABLE.search(c) and "<<" not in c]
            out_sessions.append({
                "tool": s.tool,
                "id": s.session_id[:12],
                "title": clean_prompt(s.title, 120) if s.title else None,
                "start": s.start.isoformat(timespec="minutes"),
                "end": s.end.isoformat(timespec="minutes"),
                "active_minutes": active_minutes(s.events, idle, burst),
                "days": per_day(s.events, idle, burst),
                "branch": s.branch,
                "prompts": s.prompts[: cfg["max_prompts"]],
                "prompts_omitted": max(0, len(s.prompts) - cfg["max_prompts"]),
                "files": files[: cfg["max_files"]],
                "files_omitted": max(0, len(files) - cfg["max_files"]),
                "commands": notable[: cfg["max_commands"]],
                "last_reply": clean_prompt(s.last_reply, 700) if s.last_reply else None,
                "subagents": s.subagents,
                "subtasks": s.subtasks[:10],
            })

        texts = [s.branch or "" for s in items] + [p for s in items for p in s.prompts] \
            + [s.title or "" for s in items] + [c["subject"] for c in commits]
        projects.append({
            "name": name,
            "root": _rel(root, None, None),
            "is_git": is_git,
            "active_minutes": active_minutes(events, idle, burst),
            "days": per_day(events, idle, burst),
            "first": min(events).isoformat(timespec="minutes"),
            "last": max(events).isoformat(timespec="minutes"),
            "tools": sorted({s.tool for s in items}),
            "branches": sorted({s.branch for s in items if s.branch}),
            "issue_keys": _issue_keys(texts, cfg["issue_pattern"], cfg["issue_denylist"]),
            "commits": commits,
            "sessions": out_sessions,
        })

    projects.sort(key=lambda p: p["active_minutes"], reverse=True)
    return {
        "range": {"start": start.isoformat(timespec="minutes"), "end": end.isoformat(timespec="minutes"),
                  "timezone": str(start.tzinfo)},
        "totals": {
            "active_minutes": active_minutes(all_events, idle, burst),
            "projects": len(projects),
            "sessions": sum(len(p["sessions"]) for p in projects),
            "commits": sum(len(p["commits"]) for p in projects),
            "idle_minutes_threshold": idle,
        },
        "projects": projects,
    }
