"""OpenCode and OpenChamber (a GUI on top of OpenCode, sharing its storage).

Two layouts are supported:
  * JSON files: <data>/storage/{session/<project>/<id>.json, message/<sid>/*.json, part/<mid>/*.json}
  * SQLite:     <data>/opencode.db with session / message / part tables (JSON in a `data` column)
<data> is $XDG_DATA_HOME/opencode or ~/.local/share/opencode.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from ..model import Session
from ..redact import clean_prompt, looks_injected
from ..timeparse import in_range, to_dt
from ._util import configured, first_existing, patch_files, read_json

NAME = "opencode"
LABEL = "OpenCode / OpenChamber"

EDIT_TOOLS = {"edit", "write", "patch", "multiedit", "apply_patch"}
SHELL_TOOLS = {"bash", "shell"}
SELF_COMMANDS = ("/worklog",)


def locate(cfg):
    xdg = os.environ.get("XDG_DATA_HOME")
    base = first_existing(configured(cfg, NAME),
                          Path(xdg) / "opencode" if xdg else None,
                          Path.home() / ".local" / "share" / "opencode")
    if base and ((base / "storage" / "session").is_dir() or any(base.glob("*.db"))):
        return base
    return None


def _t(obj, *keys):
    """First timestamp found among nested keys like ('time','created') or flat 'time_created'."""
    for k in keys:
        cur = obj
        for part in k.split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
        if cur is not None:
            return to_dt(cur)
    return None


def _apply_part(s: Session, part: dict, role: str, ts, start, end, limit):
    ptype = part.get("type")
    if ptype == "text" and role == "user" and not part.get("synthetic"):
        text = part.get("text") or ""
        if text.strip().startswith(SELF_COMMANDS):
            return "self"
        if text and not looks_injected(text):
            q = clean_prompt(text, limit)
            if q:
                s.add_prompt(q)
    elif ptype == "text" and role == "assistant" and part.get("text"):
        s.last_reply = part["text"]
    elif ptype == "tool":
        tool = (part.get("tool") or "").lower()
        inp = ((part.get("state") or {}).get("input")) or {}
        if tool in EDIT_TOOLS:
            s.add_file(inp.get("filePath") or inp.get("file_path") or inp.get("path"))
            for f in patch_files(inp.get("patchText") or inp.get("patch") or ""):
                s.add_file(f)
        elif tool in SHELL_TOOLS:
            s.add_command(inp.get("command"))
    return None


def _session_from(info: dict) -> Session:
    s = Session(tool=NAME, session_id=str(info.get("id")),
                cwd=info.get("directory") or info.get("cwd"),
                title=info.get("title"), parent_id=info.get("parentID") or info.get("parent_id"))
    if s.parent_id:
        s.agent = s.title
    return s


def _collect_json(base: Path, start, end, cfg, stats):
    storage = base / "storage"
    limit = cfg["prompt_chars"]
    for sp in (storage / "session").glob("*/*.json"):
        info = read_json(sp, stats)
        if not info:
            continue
        upd = _t(info, "time.updated", "time_updated")
        crt = _t(info, "time.created", "time_created")
        if (upd and upd < start) or (crt and crt >= end):
            continue
        stats["files"] = stats.get("files", 0) + 1
        s = _session_from(info)
        for mp in sorted((storage / "message" / s.session_id).glob("*.json")):
            msg = read_json(mp, stats)
            if not msg:
                continue
            ts = _t(msg, "time.created", "time_created")
            if not in_range(ts, start, end):
                continue
            s.events.append(ts)
            role = msg.get("role")
            for pp in sorted((storage / "part" / str(msg.get("id"))).glob("*.json")):
                part = read_json(pp, stats)
                if part and _apply_part(s, part, role, ts, start, end, limit) == "self":
                    s.events.pop()
                    break
        yield s


def _rows(con, table, filter_col=None, ids=None):
    cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
    sql, params = f"SELECT * FROM {table}", ()
    if filter_col and ids and filter_col in cols and len(ids) < 900:
        sql += f" WHERE {filter_col} IN ({','.join('?' * len(ids))})"
        params = tuple(ids)
    for row in con.execute(sql, params):
        d = dict(zip(cols, row))
        data = d.pop("data", None)
        if isinstance(data, (str, bytes)):
            try:
                extra = json.loads(data)
                if isinstance(extra, dict):
                    d = {**extra, **{k: v for k, v in d.items() if v is not None}}
            except json.JSONDecodeError:
                pass
        yield d


def _collect_sqlite(db: Path, start, end, cfg, stats):
    limit = cfg["prompt_chars"]
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except sqlite3.Error as e:
        stats.setdefault("errors", []).append(f"{db.name}: {e}")
        return
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"session", "message", "part"} <= tables:
            return
        stats["files"] = stats.get("files", 0) + 1
        sessions = {}
        for info in _rows(con, "session"):
            upd = _t(info, "time.updated", "time_updated")
            crt = _t(info, "time.created", "time_created")
            if (upd and upd < start) or (crt and crt >= end):
                continue
            sessions[str(info.get("id"))] = _session_from(info)
        if not sessions:
            return
        messages = {}
        for msg in _rows(con, "message", "session_id", list(sessions)):
            sid = str(msg.get("sessionID") or msg.get("session_id"))
            if sid not in sessions:
                continue
            ts = _t(msg, "time.created", "time_created")
            if in_range(ts, start, end):
                messages[str(msg.get("id"))] = (sessions[sid], msg.get("role"), ts)
                sessions[sid].events.append(ts)
        for part in _rows(con, "part", "session_id", list(sessions)):
            hit = messages.get(str(part.get("messageID") or part.get("message_id")))
            if hit:
                _apply_part(hit[0], part, hit[1], hit[2], start, end, limit)
        yield from sessions.values()
    except sqlite3.Error as e:
        stats.setdefault("errors", []).append(f"{db.name}: {e}")
    finally:
        con.close()


def collect(base: Path, start, end, cfg, stats):
    out = []
    if (base / "storage" / "session").is_dir():
        out.extend(_collect_json(base, start, end, cfg, stats))
    for db in base.glob("*.db"):
        out.extend(_collect_sqlite(db, start, end, cfg, stats))
    return out
