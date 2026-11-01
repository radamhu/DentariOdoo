#!/usr/bin/env bash
# Stop hook: block once if files changed since .agent-notes.md was last updated.
set -u
input=$(cat)
case "$input" in *'"stop_hook_active":true'*|*'"stop_hook_active": true'*) exit 0 ;; esac

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
notes=.agent-notes.md

if [ ! -f "$notes" ]; then
  reason="$notes missing. Create it with sections ## Handoff, ## Notes, ## Changelog."
else
  changed=$(find . \( -path ./.git -o -path ./.venv -o -path ./.claude -o -path ./.pytest_cache -o -path ./.superpowers -o -path ./.playwright-mcp -o -path ./.agents -o -path ./graphify-out \) -prune \
    -o -type f -newer "$notes" ! -name '.DS_Store' ! -name '*.pyc' -print 2>/dev/null | head -1)
  [ -z "$changed" ] && exit 0
  reason="Files changed since $notes was updated (e.g. $changed). Overwrite ## Handoff, prepend ## Changelog entry, update ## Notes."
fi
printf '{"decision":"block","reason":"%s"}\n' "$reason"
