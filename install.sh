#!/usr/bin/env bash
# worklog — install the skill for Claude Code (default) and/or Codex.
# Usage:
#   ./install.sh              install for Claude Code (~/.claude/skills/worklog)
#   ./install.sh --codex      install for Codex       (~/.codex/skills/worklog)
#   ./install.sh --all        both
#   ./install.sh --uninstall  remove from both
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/skills/worklog"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills"
CODEX_DIR="${CODEX_HOME:-$HOME/.codex}/skills"

install_to() {
  local dest="$1/worklog"
  mkdir -p "$1"
  rm -rf "$dest"
  cp -R "$SRC" "$dest"
  find "$dest" -name '__pycache__' -type d -prune -exec rm -rf {} +
  chmod +x "$dest/scripts/worklog.py"
  echo "  installed: $dest"
}

remove_from() {
  if [ -d "$1/worklog" ]; then rm -rf "$1/worklog"; echo "  removed: $1/worklog"; fi
}

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required (3.8+)." >&2
  exit 1
fi

case "${1:-}" in
  --uninstall) remove_from "$CLAUDE_DIR"; remove_from "$CODEX_DIR"; exit 0 ;;
  --codex)     install_to "$CODEX_DIR" ;;
  --all)       install_to "$CLAUDE_DIR"; install_to "$CODEX_DIR" ;;
  "")          install_to "$CLAUDE_DIR" ;;
  *)           echo "unknown option: $1" >&2; exit 2 ;;
esac

echo
python3 "$SRC/scripts/worklog.py" --doctor | python3 -c "$(cat <<'PY'
import json, sys
d = json.load(sys.stdin)
for s in d["sources"]:
    mark = "+" if s["status"] == "found" else "-"
    print("  %s %-24s %s" % (mark, s["label"], s["path"] or s["status"]))
PY
)"
echo
echo "Done. Restart your agent and run: /worklog today"
