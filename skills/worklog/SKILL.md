---
name: worklog
description: Scans local AI coding sessions (Claude Code, Codex, Kiro, OpenCode/OpenChamber) for a time range and writes a bullet-point report of the work done, grouped by project with time estimates, commits and issue keys. Use when the user runs /worklog or asks what they worked on in a period.
disable-model-invocation: true
---

# worklog

Turn the user's local AI coding sessions into a work report for a given period.
A bundled collector does the reading; you do the summarizing.

## 1. Resolve the time range

Map what the user asked for to collector arguments. Use the current local date (run `date`
if you are unsure of it). Default is `today`.

| User says (any language) | Argument |
|---|---|
| today, bugün | `today` |
| yesterday, dün | `yesterday` |
| this week, bu hafta | `this-week` |
| last week, geçen hafta | `last-week` |
| this month / last month | `this-month` / `last-month` |
| last N hours/days/weeks, son N saat/gün/hafta | `Nh` / `Nd` / `Nw` |
| a date, or from–to | `2026-11-03` or `2026-11-01..2026-11-05` |
| since Monday 09:00, specific hours | `--since 2026-11-02T09:00 --until now` |

Extra filters the user may give: a project name → `--project <text>`; only some tools →
`--sources claude,codex`.

## 2. Run the collector

The collector is `scripts/worklog.py` in this skill's directory (usually
`~/.claude/skills/worklog/scripts/worklog.py`, or `~/.codex/skills/worklog/...` in Codex).
It needs only Python 3.8+ and git, reads files read-only, and prints JSON to stdout.

```bash
python3 <skill-dir>/scripts/worklog.py <range> [--project X] [--sources a,b]
```

- If the JSON has `"projects": []`, say no AI session activity was found in that range and list
  which sources were found (`sources[].status`). Stop there.
- If a source shows `errors`, mention it in one line at the end; do not stop.
- For ranges longer than ~3 weeks, run it per project or per week if the output is very large.
- Run `--doctor` only when the user asks why a tool is missing.

## 3. What the JSON contains

`projects[]` sorted by time spent. Each project has `active_minutes`, `days` (minutes per date),
`tools`, `branches`, `issue_keys`, `commits` (your commits in range, all branches) and
`sessions[]`. Each session has `tool`, `title`, `start`/`end`, `active_minutes`, `prompts`
(the user's own requests, cleaned and masked), `files` (edited, relative to repo root),
`commands` (notable: tests, builds, git, deploys), `last_reply` (the agent's final message,
usually the best statement of what got done), `subtasks` (subagent/workflow names merged in).

`active_minutes` already excludes idle gaps (default > 30 min) and merges parallel sessions,
so never add session minutes together to get a project total; use the project value. Session
minutes can sum to more than the project when sessions overlap; scale bullets down to fit.
Sessions also carry their own `days`, so per-day rows can be split per session.

`range.end` is exclusive: `2026-10-01..2026-10-16` ends at `2026-10-17T00:00` and means 1–16 Oct.
`is_git: false` means the folder isn't a git repo, so there is no commit data (say "no git repo",
not "0 commits"). `prompts` can be empty when only the agent's own threads fell in range; rely on
`title`, `last_reply` and `files` then.

## 4. Write the report

Default format is below. Write in the user's language. Keep it scannable; this is going
into a work tracker or a standup, not a novel.

```
## Worklog · <range in words> · ≈<total h m> · <N> projects

### <project> · ≈<time> · <branch(es)> · <ISSUE-1, ISSUE-2>
- ✅ <ISSUE-KEY> <what was achieved, past tense, outcome first> (≈<time>, <n> commits)
- 🔄 <work that changed files but isn't finished/committed> (≈<time>)
- 🔍 <analysis, debugging or research with no file changes> (≈<time>)
```

How to build the bullets:

1. **One bullet per piece of work, not per session or per prompt.** Merge sessions and tools
   that served the same goal (same issue key, same files, or clearly the same feature). Split
   one long session into several bullets when it covered unrelated things.
2. **Outcome first.** "Added coupon support to checkout" not "Asked Codex to add coupons".
   Derive it from `last_reply`, commit subjects, `files` and `prompts`, in that order of trust.
3. **Status:**
   - ✅ a commit covers it, or `last_reply` reports it finished (tests/build passed, review
     approved) and files changed. If done but not committed, add "(not committed)".
   - 🔄 files changed but the work isn't finished: no completion statement, a follow-up step
     (deploy, migration, review) is still pending, or the user's last request wasn't answered
   - 🔍 no files changed (investigation, review, planning, Q&A)
4. **Issue keys:** put a key at the start of a bullet only when it is clearly tied to that work
   (in the branch, commit subject or prompt for it). Never invent keys.
5. **Time:** round to 5 minutes, write as `≈1h 20m` in the user's language (Turkish: `≈1s 20dk`).
   Dates use the user's language with short weekday names (`Mon 3 Nov`, `Pzt 3 Kas`).
   When a bullet spans part of a session, split that session's minutes by judgment; the
   bullets of a project should roughly add up to the project total.
6. **Evidence, briefly:** commit count, and at most 2–3 key file or module names when they
   help identify the work. No file dumps, no command dumps, no raw prompt quotes.
7. **Commits not covered by any session** (made by hand) get their own ✅ bullets from the
   commit subjects.
8. For multi-day ranges add a short per-day line under each project from `days`
   (e.g. `Mon 3 Nov ≈2h · Tue 4 Nov ≈40m`), or a day-by-day section if the user asked "per day".

Close with one line: total active time, number of commits, and which tools the data came from.

### Alternative formats (when the user asks)

- **standup**: three headings, *Done* (✅ items), *In progress* (🔄 items), *Blockers*
  (only if prompts or replies mention one), one line per item.
- **table / tablo**: a Markdown table with columns `Date | Project | Issue | Work item | Time | Status`,
  one row per bullet per day, ready to paste into a tracker.
- **short / kısa**: one line per project with its time and the 1–3 main outcomes.

## Rules

- Base everything on the collector output. If something is unclear, describe it plainly
  ("worked on the payment webhook") rather than guessing details.
- Times are estimates from activity timestamps; say "≈" and never present them as exact.
- Never print secrets. The collector masks known patterns; if you still notice a credential,
  leave it out. Also leave out IP addresses, server host names, SSH targets, internal URLs and
  personal data from prompts: the report is meant to be shared.
- `prompts` may contain pasted logs or errors; summarize what the problem was, don't quote them.
- Don't paste the JSON or the user's prompts verbatim into the report.
- The report is the final answer. Don't write files unless the user asks for one.
