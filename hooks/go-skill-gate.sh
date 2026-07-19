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
wires=( "${KIMI_CODE_HOME:-$HOME/.kimi-code}/sessions"/*/"$session_id"/agents/*/wire.jsonl )
shopt -u nullglob
[ "${#wires[@]}" -gt 0 ] || exit 0

for wire in "${wires[@]}"; do
  [ -f "$wire" ] && [ ! -L "$wire" ] || continue
  # Single grep, no pipeline: with a producer|grep -q pipe, grep exits on
  # the first match and the producer dies by SIGPIPE once the pipe buffer
  # (64KB default here) fills — timing-dependent, and under pipefail the
  # pipeline status false-denies. LC_ALL=C keeps '.' byte-exact: on this
  # host (GNU grep 3.11) a UTF-8 locale refuses to match a record line
  # whose spanned region contains invalid bytes, which would false-deny;
  # test_go_skill_gate_allows_with_invalid_byte_in_record_line pins this.
  # Anchored to the tool.call record with "name":"Skill","args": adjacency
  # so snapshot lines and nested mentions without that exact adjacency
  # cannot false-pass; test_go_skill_gate_denies_nested_mention_in_tool_call
  # pins that nested case. Residual accepted hole: a nested unescaped
  # mention reproducing the full "name":"Skill","args":{"skill":"go-coding-style"
  # byte sequence inside another tool.call still false-passes; closing it
  # needs JSON parsing in a deliberately fail-open, grep-only gate.
  # Byte-order coupled to the wire format; the real-wire drift probe
  # and go_gate_real_skill_record pin a byte-exact captured record —
  # update all on wire-format drift.
  if LC_ALL=C grep -qE '"type":"tool[.]call".*"name":"Skill","args":\{"skill":"go-coding-style"[},]' -- "$wire" 2>/dev/null; then
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
