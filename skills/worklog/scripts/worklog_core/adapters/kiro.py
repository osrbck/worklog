"""Kiro (IDE and CLI): ~/.kiro/sessions/<workspace-hash>/sess_<uuid>/{session.json,messages.jsonl}."""

from __future__ import annotations

from pathlib import Path

from ..model import Session
from ..redact import clean_prompt, looks_injected
from ..timeparse import in_range, to_dt
from ._util import configured, env_path, first_existing, iter_jsonl, read_json

NAME = "kiro"
LABEL = "Kiro"

EDIT_NAMES = {"fs_write", "fs_append", "fs_create", "str_replace", "strReplace", "create_file",
              "write_file", "edit_file", "delete_file", "fs_delete", "apply_patch"}
SHELL_NAMES = {"execute_bash", "executeBash", "run_command", "shell"}
SELF_COMMANDS = ("/worklog",)


def locate(cfg):
    base = first_existing(configured(cfg, NAME), env_path("KIRO_HOME"), Path.home() / ".kiro")
    return base / "sessions" if base and (base / "sessions").is_dir() else None


def collect(root: Path, start, end, cfg, stats):
    out = []
    limit = cfg["prompt_chars"]
    for meta_path in root.glob("*/sess_*/session.json"):
        meta = read_json(meta_path, stats)
        if not meta:
            continue
        created, modified = to_dt(meta.get("createdAt")), to_dt(meta.get("lastModifiedAt"))
        if (modified and modified < start) or (created and created >= end):
            continue
        msgs = meta_path.parent / "messages.jsonl"
        if not msgs.is_file():
            continue
        stats["files"] = stats.get("files", 0) + 1
        paths = meta.get("workspacePaths") or meta.get("rootPaths") or []
        title = meta.get("title")
        s = Session(tool=NAME, session_id=meta.get("id") or meta_path.parent.name,
                    cwd=paths[0] if paths else None,
                    title=None if not title or title == "New Session" else title)
        root_id = meta.get("rootConversationId")
        if root_id and root_id != s.session_id:
            s.parent_id = root_id
            wf = (((meta.get("_meta") or {}).get("kiro") or {}).get("workflow") or {})
            s.agent = wf.get("workflowName") or (title or "").split(" · ")[0] or meta.get("agentMode")
        for r in iter_jsonl(msgs, stats):
            ts = to_dt(r.get("timestamp"))
            if not in_range(ts, start, end):
                continue
            p = r.get("payload") or {}
            ptype = p.get("type")
            if ptype in ("session_metadata", "usage_summary", "context_snapshot"):
                continue
            s.events.append(ts)
            if ptype == "user":
                kmeta = ((p.get("_meta") or {}).get("kiro") or {})
                if "userMessageTag" not in kmeta or kmeta.get("notification") \
                        or kmeta.get("syntheticUserMessageReason"):
                    continue
                text = p.get("content") if isinstance(p.get("content"), str) else ""
                if not text or looks_injected(text):
                    continue
                if text.strip().startswith(SELF_COMMANDS):
                    s.events.pop()
                    continue
                q = clean_prompt(text, limit)
                if q:
                    s.add_prompt(q)
            elif ptype == "tool_call":
                name, args = p.get("toolName") or "", p.get("args") or {}
                if p.get("kind") == "edit" or name in EDIT_NAMES:
                    s.add_file(args.get("path") or args.get("filePath") or args.get("file_path"))
                    for extra in args.get("paths") or []:
                        s.add_file(extra if isinstance(extra, str) else None)
                elif p.get("kind") == "execute" or name in SHELL_NAMES:
                    s.add_command(args.get("command"))
            elif ptype == "assistant" and p.get("operationType") != "Reasoning":
                if isinstance(p.get("content"), str) and p["content"].strip():
                    s.last_reply = p["content"]
        out.append(s)
    return out
