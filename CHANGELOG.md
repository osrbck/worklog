# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-11-06

### Added
- `/worklog` skill for Claude Code and Codex
- Collector with adapters for Claude Code, Codex, Kiro and OpenCode/OpenChamber (experimental)
- Subagent (Claude, Codex) and workflow (Kiro) threads folded into their root session
- Idle-aware time estimates per session, project and day; parallel sessions not double counted
- Git commit lookup per repo, issue key detection, secret masking
- Report formats: default bullets, standup, table, short
- `--doctor`, `--project`, `--sources`, config file, installer with `--codex` / `--all` / `--uninstall`
