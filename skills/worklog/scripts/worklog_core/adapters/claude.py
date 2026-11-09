"""Claude Code: ~/.claude/projects/<encoded-cwd>/<session>.jsonl (+ <session>/subagents/*.jsonl)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict

from ..model import Session
from ..redact import clean_prompt, looks_injected
from ..timeparse import in_range, to_dt
from ._util import configured, env_path, first_existing, iter_jsonl, modified_since

NAME = "claude"
LABEL = "Claude Code"

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "str_replace_based_edit_tool"}
SHELL_TOOLS = {"Bash", "PowerShell"}
_CMD_NAME = re.compile(r"<command-name>\s*(/?[^<\s]+)\s*</command-name>")
_CMD_ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.S)
SELF_COMMANDS = ("/worklog",)


def locate(cfg):
    base = first_existing(configured(cfg, NAME), env_path("CLAUDE_CONFIG_DIR"), Path.home() / ".claude")
    if base and (base / "projects").is_dir():
        return base / "projects"
    return None


def _user_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        if any(isinstance(c, dict) and c.get("type") == "tool_result" for c in content):
            return ""
        return "\n".join(c.get("text", "") for c in content
                         if isinstance(c, dict) and c.get("type") == "text")
    return ""


def _normalize_prompt(text: str):
    """Return (prompt, is_self). Slash commands become '/name args'."""
    m = _CMD_NAME.search(text)
    if m:
        name = m.group(1) if m.group(1).startswith("/") else "/" + m.group(1)
        args = _CMD_ARGS.search(text)
        text = (name + " " + (args.group(1).strip() if args else "")).strip()
        return text, name in SELF_COMMANDS
    if "<local-command-stdout>" in text or text.startswith("Caveat: The messages below"):
        return "", False
    stripped = text.strip()
    return text, any(stripped.startswith(c) for c in SELF_COMMANDS)


def collect(root: Path, start, end, cfg, stats):
    sessions: Dict[str, Session] = {}
    limit = cfg["prompt_chars"]
    for path in root.rglob("*.jsonl"):
        if not modified_since(path, start):
            continue
        stats["files"] = stats.get("files", 0) + 1
        for r in iter_jsonl(path, stats):
            rtype = r.get("type")
            sid = r.get("sessionId")
            if rtype == "summary" and r.get("summary"):
                # summaries reference a leaf uuid, not a session; keep as a title candidate
                stats.setdefault("_titles", {})[r.get("leafUuid")] = r["summary"]
                continue
            if rtype not in ("user", "assistant") or not sid:
                continue
            ts = to_dt(r.get("timestamp"))
            if not in_range(ts, start, end):
                continue
            s = sessions.get(sid)
            if s is None:
                s = sessions[sid] = Session(tool=NAME, session_id=sid)
            s.cwd = s.cwd or r.get("cwd")
            br = r.get("gitBranch")
            if br and br != "HEAD":
                s.branch = br
            s.events.append(ts)
            msg = r.get("message") or {}
            content = msg.get("content")

            if rtype == "user":
                if r.get("isMeta") or r.get("isSidechain") or r.get("isCompactSummary"):
                    continue
                text = _user_text(content)
                if not text or looks_injected(text):
                    continue
                text, is_self = _normalize_prompt(text)
                if is_self:
                    s.events.pop()          # the /worklog call itself isn't work
                    continue
                p = clean_prompt(text, limit)
                if p:
                    s.add_prompt(p)
                continue

            if not isinstance(content, list):
                continue
            for c in content:
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "tool_use":
                    name, inp = c.get("name"), c.get("input") or {}
                    if name in EDIT_TOOLS:
                        s.add_file(inp.get("file_path") or inp.get("notebook_path") or inp.get("path"))
                    elif name in SHELL_TOOLS:
                        s.add_command(inp.get("command"))
                elif c.get("type") == "text" and c.get("text") and not r.get("isSidechain"):
                    s.last_reply = c["text"]
    stats.pop("_titles", None)
    return sessions.values()
