"""Source adapters. Each module exposes:

    NAME: str                       # short id used in config and output
    LABEL: str                      # human readable name
    def locate(cfg) -> Path | None  # data directory, or None when the tool isn't installed
    def collect(root, start, end, cfg, stats) -> Iterable[Session]

Adapters must be read-only, tolerate unknown/changed record shapes (skip, never crash),
and only emit activity that falls inside [start, end).
"""

from . import claude, codex, kiro, opencode

ADAPTERS = {m.NAME: m for m in (claude, codex, kiro, opencode)}
