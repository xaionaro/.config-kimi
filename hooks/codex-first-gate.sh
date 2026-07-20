#!/usr/bin/env bash
set -u

deny() {
  printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Codex-first enforcement denied Agent/AgentSwarm: delegated work must use ~/.kimi-code/bin/codex-with-rotation via Bash. Authorization requires one fresh marker under ~/.cache/kimi-proof/$SESSION_ID/cyber-escalation/: the wrapper-emitted <task_sig> after exit 75, or orchestration-<role>-<nonce> before an approved ECI/ATE non-Codex role spawn. Markers are one-use and expire after 600s. CODEX_KIMI_FORCE=1 disables enforcement for this process; use only for debugging or known-broken codex."}}'
  exit 0
}

[[ ${CODEX_KIMI_FORCE:-0} == 1 ]] && exit 0
command -v jq >/dev/null && command -v flock >/dev/null || deny
input=$(cat) || deny
sid=$(jq -er '.session_id|select(type=="string" and test("^[A-Za-z0-9._-]+$"))' <<<"$input") || deny
dir="$HOME/.cache/kimi-proof/$sid/cyber-escalation"
[[ -d $dir && ! -L $dir ]] || deny

exec {dfd}<"$dir" || deny
flock -x "$dfd" || deny
now=$(date +%s) || deny
shopt -s nullglob

for p in "$dir"/*; do
  [[ -f $p && ! -L $p ]] || continue
  n=${p##*/}
  [[ $n =~ ^[0-9a-f]{64}$ ||
     $n =~ ^orchestration-(critic-step2|critic-A|critic-B|e2e-gate|brainstormer|loop-breaker|brp-feasibility-validator)-[0-9a-f]{16}$ ]] || continue
  IFS= read -r ts <"$p" || ts=
  if [[ $ts =~ ^[0-9]+$ ]] && (( ts <= now && now-ts <= 600 )); then
    rm -- "$p" 2>/dev/null && exit 0       # unlink claims once
  elif [[ $ts =~ ^[0-9]+$ ]] && (( now-ts > 600 )); then
    rm -- "$p" 2>/dev/null || :            # lazy expiry
  fi
done
deny
