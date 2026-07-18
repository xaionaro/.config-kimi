#!/usr/bin/env bash
# PreToolUse hook: deny .go edits until go-coding-style is loaded in this session.
# Detection scans the session's per-agent wire files for the Skill tool.call
# record; hook payloads carry no transcript_path or agent identity, so the
# wires are located by session_id and the check is session-scoped.

set -euo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HOOK_DIR/lib/codex-proof-state.sh"

input=$(cat)
tool_name=$(printf '%s' "$input" | jq -r '.tool_name // empty' 2>/dev/null || true)

case "$tool_name" in
  Edit|Write) ;;
  *) exit 0 ;;
esac

file_path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.path // .tool_input.target_file // empty' 2>/dev/null || true)
case "$file_path" in
  *.go) ;;
  *) exit 0 ;;
esac

session_id=$(printf '%s' "$input" | jq -r '.session_id // empty' 2>/dev/null || true)
codex_valid_session_id "$session_id" || exit 0

shopt -s nullglob
wires=( "$HOME/.kimi-code/sessions"/*/"$session_id"/agents/*/wire.jsonl )
shopt -u nullglob
[ "${#wires[@]}" -gt 0 ] || exit 0

for wire in "${wires[@]}"; do
  [ -f "$wire" ] && [ ! -L "$wire" ] || continue
  if grep -F '"name":"Skill"' -- "$wire" 2>/dev/null |
     grep -qE '"skill":"go-coding-style"[},]'; then
    exit 0
  fi
done

jq -n --arg reason "Do not edit .go files before loading the go-coding-style skill in this session. Invoke the Skill tool with go-coding-style, then retry." '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason: $reason
  }
}'
exit 0
