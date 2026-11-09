# worklog

**Turn your AI coding sessions into a work report.** `/worklog` reads the sessions you ran in
Claude Code, Codex, Kiro and OpenCode/OpenChamber on your machine and writes a bullet list of what
got done in a period, grouped by project, with time estimates, commits and issue keys.

> 🇹🇷 Türkçe: [README.tr.md](README.tr.md)

```
/worklog yesterday
```

```
## Worklog · Thu 5 Nov · ≈5h 40m · 3 projects

### shop-api · ≈3h 10m · feat/SHOP-42-cart · SHOP-42, SHOP-45
- ✅ SHOP-42 Fixed cart total rounding and added coupon support (≈1h 50m, 3 commits)
- 🔄 SHOP-45 Started the checkout page; form and validation done, payment step pending (≈1h 05m)
- 🔍 Investigated the flaky webhook test, traced it to a clock-dependent fixture (≈15m)

### portfolio · ≈1h 30m · main
- ✅ Added the agentack project card with cover image (≈40m, 1 commit)
...
Total ≈5h 40m · 6 commits · Claude Code, Codex, Kiro
```

## How it works

```
/worklog <range>
   │
   ├─ 1. collector (Python, stdlib only, read-only)
   │     adapters ── claude · codex · kiro · opencode
   │     → one model: project, branch, your requests, files edited, notable commands,
   │       final agent reply, activity timestamps
   │     → secrets masked, injected context stripped, subagent/workflow threads folded in
   │
   ├─ 2. git: your commits in each detected repo for the same range (all branches)
   │
   └─ 3. the agent writes the report from that compact JSON digest
```

- **Done vs. discussed.** Commits and changed files decide the status: ✅ done, 🔄 in progress,
  🔍 research/analysis.
- **Realistic time.** Gaps longer than 30 minutes count as idle. Parallel sessions in the same
  project aren't double counted.
- **One item per piece of work.** The same feature worked on in Claude and then Codex becomes a
  single bullet.
- **Issue keys** (`ABC-123`) are picked up from branches, commit messages and your requests.

## Supported tools

| Tool | Data read | Status |
|---|---|---|
| Claude Code | `~/.claude/projects/**/*.jsonl` (incl. subagents) | ✅ tested |
| Codex (CLI and IDE) | `~/.codex/sessions/**/rollout-*.jsonl` + `session_index.jsonl` | ✅ tested |
| Kiro (IDE and CLI) | `~/.kiro/sessions/*/sess_*/` (incl. workflow runs) | ✅ tested |
| OpenCode / OpenChamber | `~/.local/share/opencode` (JSON storage or SQLite) | 🧪 experimental |

Tools that aren't installed are skipped. Locations can be overridden (see [Configuration](#configuration)),
and `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `KIRO_HOME` and `XDG_DATA_HOME` are honored.

## Install

Requirements: Python 3.8+, git, and Claude Code or Codex. macOS, Linux and WSL.

```bash
git clone https://github.com/osrbck/worklog.git ~/worklog
~/worklog/install.sh          # Claude Code
~/worklog/install.sh --codex  # Codex
~/worklog/install.sh --all    # both
```

The installer prints which session sources it found. Update with
`cd ~/worklog && git pull && ./install.sh`, remove with `./install.sh --uninstall`.

## Usage

```
/worklog                       today
/worklog yesterday
/worklog this week             (or: last week, this month, last 3 days, 2026-11-01..2026-11-05)
/worklog since Monday 09:00
/worklog last week for shop-api
/worklog yesterday standup     Done / In progress / Blockers
/worklog this week table       Date | Project | Issue | Work item | Time | Status
```

Natural language works in any language ("dün", "bu hafta", "son 3 gün"). The collector can also
be run by hand:

```bash
python3 ~/.claude/skills/worklog/scripts/worklog.py yesterday --pretty
python3 ~/.claude/skills/worklog/scripts/worklog.py --doctor
```

## Privacy

- The collector only **reads** files and runs read-only `git log`. It makes no network requests.
- Raw transcripts never reach the model. The agent sees a compact digest: your requests (cut to
  280 characters), file paths, notable commands and the final agent reply, with known secret
  formats masked (API keys, tokens, JWTs, private keys, `PASSWORD=` style assignments,
  credentials in URLs).
- That digest is part of your conversation with the agent, so it goes wherever that agent sends
  its conversations. Leave sensitive projects out with `exclude_projects`.

## Configuration

Optional. Create `~/.config/worklog/config.json`; every key is optional:

```json
{
  "sources": ["claude", "codex", "kiro", "opencode"],
  "paths": { "codex": "/mnt/d/Users/me/.codex" },
  "exclude_projects": ["*/clients/secret-*", "dotfiles"],
  "idle_minutes": 30,
  "min_burst_minutes": 5,
  "issue_pattern": "\\b[A-Z][A-Z0-9]{1,9}-\\d{1,6}\\b",
  "git_authors": ["me@work.com", "me@personal.dev"],
  "max_prompts": 8,
  "prompt_chars": 280
}
```

`git_authors` defaults to each repo's `git config user.email`.

## Adding a tool

Each tool is one file in `skills/worklog/scripts/worklog_core/adapters/` with a `locate()` and a
`collect()` function that yields `Session` objects. See [CONTRIBUTING.md](CONTRIBUTING.md).

```bash
python3 -m unittest discover -s tests -v
```

## License

[MIT](LICENSE). worklog is a community project and isn't affiliated with Anthropic, OpenAI, AWS or
the OpenCode project.
