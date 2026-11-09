"""User configuration: ~/.config/worklog/config.json (all keys optional)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

DEFAULTS: Dict[str, Any] = {
    # adapters to run; unknown/missing tools are skipped silently
    "sources": ["claude", "codex", "kiro", "opencode"],
    # override data locations, e.g. {"codex": "/mnt/d/.codex"}
    "paths": {},
    # glob patterns (matched against project root path or name) to leave out
    "exclude_projects": [],
    # gaps longer than this between activity events are idle time
    "idle_minutes": 30,
    # minutes credited to an isolated burst of activity
    "min_burst_minutes": 5,
    # issue key detection
    "issue_pattern": r"\b[A-Z][A-Z0-9]{1,9}-\d{1,6}\b",
    "issue_denylist": ["UTF", "SHA", "ISO", "RFC", "HTTP", "TLS", "SSL", "AES", "RSA",
                       "UUID", "ES", "PEP", "CVE", "GPT", "WIN", "X86", "ARM", "LTS", "COVID"],
    # git author emails to count as "you"; empty = each repo's `git config user.email`
    "git_authors": [],
    # output size limits per session
    "max_prompts": 8,
    "max_files": 30,
    "max_commands": 8,
    "prompt_chars": 280,
}

# commands worth reporting (everything else is exploration noise)
NOTABLE_COMMAND = (r"\bgit\s+(commit|push|merge|rebase|tag|cherry-pick|revert)\b|"
                   r"\b(npm|pnpm|yarn|bun)\s+(run\s+)?(test|build|lint|e2e|deploy|migrate)|"
                   r"\b(go\s+(test|build)|cargo\s+(test|build)|pytest|vitest|jest|playwright\s+test|"
                   r"make\s+\w+|docker\s+(build|compose)|kubectl\s+apply|terraform\s+apply|"
                   r"prisma\s+migrate|goose\s+up|alembic\s+upgrade|ng\s+(build|test)|next\s+build)\b")


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(Path.home(), ".config")
    return Path(base) / "worklog" / "config.json"


def load() -> Dict[str, Any]:
    cfg = dict(DEFAULTS)
    p = config_path()
    if p.is_file():
        try:
            user = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(user, dict):
                cfg.update(user)
        except (OSError, json.JSONDecodeError) as e:
            cfg["_config_error"] = f"{p}: {e}"
    return cfg
