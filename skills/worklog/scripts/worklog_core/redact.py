"""Secret masking and text cleanup applied to everything that leaves the collector."""

from __future__ import annotations

import re

_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(r"\b(sk|rk|pk)-[A-Za-z0-9_\-]{16,}"),                 # OpenAI/Anthropic/Stripe style
    re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),                     # GitHub tokens
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bglpat-[A-Za-z0-9_\-]{16,}"),                      # GitLab
    re.compile(r"\bxox[abposr]-[A-Za-z0-9\-]{10,}"),                 # Slack
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                             # AWS access key id
    re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"),                        # Google API key
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),  # JWT
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{16,}"),
]
_URL_CREDS = re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://)[^\s:/@]+:[^\s@/]+@")
_ASSIGN = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:PASSWORD|PASSWD|SECRET|TOKEN|API_?KEY|ACCESS_?KEY|PRIVATE_?KEY|CLIENT_?SECRET)[A-Z0-9_]*)"
    r"(\s*[:=]\s*)(['\"]?)[^\s'\"]{4,}\3"
)
_TAGS = re.compile(r"<(system-reminder|environment_context|session_context|user_instructions|"
                   r"local-command-stdout|local-command-stderr)>.*?</\1>", re.S)
_ANY_TAG_BLOCK = re.compile(r"<([a-z_\-]+)>.*?</\1>", re.S)
_WS = re.compile(r"\s+")


def redact(text: str) -> str:
    if not text:
        return text
    for p in _PATTERNS:
        text = p.sub("[REDACTED]", text)
    text = _URL_CREDS.sub(lambda m: m.group(1) + "[REDACTED]@", text)
    text = _ASSIGN.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", text)
    return text


def clean_prompt(text: str, limit: int = 280) -> str:
    """Strip injected context blocks, collapse whitespace, mask secrets, truncate."""
    if not text:
        return ""
    text = _TAGS.sub(" ", text)
    text = _WS.sub(" ", text).strip()
    text = redact(text)
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def looks_injected(text: str) -> bool:
    """True when a 'user' message is only machine-injected context."""
    stripped = _ANY_TAG_BLOCK.sub("", text or "").strip()
    return not stripped
