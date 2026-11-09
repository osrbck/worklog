# Contributing

Most contributions are new adapters or fixes for changed session formats. Tools change their
on-disk formats often, so small, well-tested adapters matter more than clever ones.

## Adapter contract

Create `skills/worklog/scripts/worklog_core/adapters/<tool>.py` and register it in
`adapters/__init__.py`.

```python
NAME = "mytool"           # id used in config and output
LABEL = "My Tool"         # shown in --doctor

def locate(cfg) -> Path | None:
    """Return the data directory, or None when the tool isn't installed."""

def collect(root, start, end, cfg, stats) -> Iterable[Session]:
    """Yield one Session per conversation with activity in [start, end)."""
```

Rules:

1. **Read-only.** Never write, lock or migrate the tool's files. Open SQLite with `mode=ro`.
2. **Never crash.** Skip records you don't understand. Put problems in `stats["errors"]`.
3. **Only real user requests go in `prompts`.** Filter out injected context, tool results,
   notifications, synthetic messages and subagent instructions. Use `add_prompt()` (dedupes).
4. **Only activity inside the range.** Check each record's timestamp with `in_range`.
5. **Be cheap.** Skip files by mtime or session metadata before parsing; stream large files.
6. **Subagents / workflows** set `parent_id` (and `agent`) so they fold into the root session.
7. Pass all user text through `clean_prompt()`; it strips tags and masks secrets.

## Tests

Add a synthetic fixture for your tool in `tests/test_worklog.py` (never commit real transcripts)
and cover: prompt filtering, file edits, commands, subagent merge, out-of-range records.

```bash
python3 -m unittest discover -s tests -v
```

## Pull requests

Describe the tool version you tested against and what a real session looked like (shape only,
no content). Update `CHANGELOG.md` under "Unreleased".
