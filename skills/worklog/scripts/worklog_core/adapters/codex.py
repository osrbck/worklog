"""OpenAI Codex CLI / IDE: ~/.codex/sessions/YYYY/MM/DD/rollout-<ts>-<id>.jsonl."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict

from ..model import Session
from ..redact import clean_prompt, looks_injected
from ..timeparse import in_range, local_tz, to_dt
from ._util import (configured, env_path, first_existing, iter_jsonl, modified_since,
                    patch_files)

NAME = "codex"
LABEL = "Codex"

_NAME_TS = re.compile(r"rollout-(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2})")
_JS_CMD = re.compile(r"exec_command\(\s*\{\s*\"?cmd\"?\s*:\s*(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|`[^`]*`)", re.S)
SELF_COMMANDS = ("/worklog", "$worklog")


def locate(cfg):
    base = first_existing(configured(cfg, NAME), env_path("CODEX_HOME"), Path.home() / ".codex")
    return base if base and (base / "sessions").is_dir() else None


def _titles(root: Path, stats) -> Dict[str, str]:
    out = {}
    idx = root / "session_index.jsonl"
    if idx.is_file():
        for r in iter_jsonl(idx, stats):
            if r.get("id") and r.get("thread_name"):
                out[r["id"]] = r["thread_name"]
    return out


def _unquote(s: str) -> str:
    if s[0] == "`":
        return s[1:-1]
    try:
        return json.loads(s if s[0] == '"' else '"' + s[1:-1].replace('"', '\\"') + '"')
    except json.JSONDecodeError:
        return s[1:-1]


def _commands_from(text: str):
    cmds = [_unquote(m) for m in _JS_CMD.findall(text or "")]
    if not cmds and text and text.lstrip().startswith("{"):
        try:  # legacy `shell` tool: {"command": ["bash", "-lc", "..."]}
            args = json.loads(text)
            c = args.get("command") or args.get("cmd")
            if isinstance(c, list) and c:
                cmds.append(c[-1] if len(c) > 2 and c[1] in ("-lc", "-c") else " ".join(map(str, c)))
            elif isinstance(c, str):
                cmds.append(c)
        except (json.JSONDecodeError, AttributeError):
            pass
    return cmds


def _files(rollouts_root: Path):
    for sub in ("sessions", "archived_sessions"):
        d = rollouts_root / sub
        if d.is_dir():
            yield from d.rglob("rollout-*.jsonl")


def collect(root: Path, start, end, cfg, stats):
    titles = _titles(root, stats)
    sessions: Dict[str, Session] = {}
    limit = cfg["prompt_chars"]
    for path in _files(root):
        m = _NAME_TS.search(path.name)
        if m:
            began = datetime.strptime(m.group(1), "%Y-%m-%dT%H-%M-%S").replace(tzinfo=local_tz())
            if began >= end:
                continue
        if not modified_since(path, start):
            continue
        stats["files"] = stats.get("files", 0) + 1
        s = None
        for r in iter_jsonl(path, stats):
            rtype, p = r.get("type"), r.get("payload") or {}
            if rtype == "session_meta":
                if s is not None:
                    continue  # later metas describe the thread this one was forked from
                sid = p.get("id") or path.stem
                s = sessions.get(sid) or Session(tool=NAME, session_id=sid)
                sessions[sid] = s
                s.cwd = p.get("cwd") or s.cwd
                s.branch = (p.get("git") or {}).get("branch") or s.branch
                s.title = titles.get(sid) or s.title
                if p.get("thread_source") == "subagent" or p.get("agent_path"):
                    s.parent_id = p.get("session_id") or p.get("parent_thread_id")
                    s.agent = (p.get("agent_path") or "").rsplit("/", 1)[-1] or p.get("agent_nickname") or None
                    if s.parent_id == s.session_id:
                        s.parent_id = None
                    s.title = s.title or titles.get(s.parent_id)
                continue
            if s is None or rtype not in ("response_item", "event_msg"):
                continue
            ts = to_dt(r.get("timestamp"))
            if not in_range(ts, start, end):
                continue
            ptype = p.get("type")
            if ptype in ("token_count",):
                continue
            s.events.append(ts)

            if ptype == "message" and p.get("role") == "user":
                meta = r.get("metadata") or {}
                if meta.get("inherited_user_message") or s.parent_id:
                    continue
                kinds = (p.get("internal_chat_message_metadata_passthrough") or {}).get("content_item_kinds")
                if kinds is not None and "user.text" not in kinds:
                    continue
                text = "\n".join(c.get("text", "") for c in (p.get("content") or [])
                                 if isinstance(c, dict) and c.get("type") == "input_text")
                if not text or looks_injected(text):
                    continue
                if text.strip().startswith(SELF_COMMANDS):
                    s.events.pop()
                    continue
                q = clean_prompt(text, limit)
                if q:
                    s.add_prompt(q)
            elif ptype in ("custom_tool_call", "function_call", "local_shell_call"):
                body = p.get("input") or p.get("arguments") or ""
                if isinstance(body, dict):
                    body = json.dumps(body)
                for f in patch_files(body):
                    s.add_file(f)
                action = p.get("action") or {}
                if isinstance(action.get("command"), list):
                    s.add_command(" ".join(map(str, action["command"][-1:])))
                for c in _commands_from(body if p.get("name") != "apply_patch" else ""):
                    s.add_command(c)
            elif ptype == "task_complete" and p.get("last_agent_message"):
                s.last_reply = p["last_agent_message"]
            elif ptype == "message" and p.get("role") == "assistant" and p.get("phase") == "final_answer":
                txt = "\n".join(c.get("text", "") for c in (p.get("content") or []) if isinstance(c, dict))
                if txt:
                    s.last_reply = txt
    return sessions.values()
