#!/usr/bin/env bash
# PreToolUse hook: lead/coordinator roles orchestrate; they do not edit.

set -euo pipefail

input=$(cat)
tool_name=$(printf '%s' "$input" | jq -r '.tool_name // empty' 2>/dev/null || true)

case "$tool_name" in
  Edit|Write) ;;
  *) exit 0 ;;
esac

case "${KIMI_ROLE:-}" in
  lead|coordinator)
    jq -n --arg role "$KIMI_ROLE" '{
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "deny",
        permissionDecisionReason: ("KIMI_ROLE=" + $role + " is an orchestration role. Assign edits to an executor/worker role instead of editing directly.")
      }
    }'
    ;;
esac
