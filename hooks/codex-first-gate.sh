#!/usr/bin/env bash
set -u

deny() {
  printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Codex-first enforcement denied Agent/AgentSwarm: delegated work must use ~/.kimi-code/bin/codex-with-rotation via Bash. Authorization requires one fresh marker under the configured KIMI_PROOF_ROOT (default ~/.cache/kimi-proof) session cyber-escalation directory: the wrapper-emitted <task_sig> after exit 75, or orchestration-<role>-<nonce> before an approved ECI/ATE non-Codex role spawn. Approved orchestration roles are loaded from ~/.kimi-code/lib/codex-roles.txt. Markers are one-use and expire after 600s. CODEX_KIMI_FORCE=1 disables enforcement for this process; use only for debugging or known-broken codex."}}'
  exit 0
}

[[ ${CODEX_KIMI_FORCE:-0} == 1 ]] && exit 0
command -v jq >/dev/null && command -v flock >/dev/null || deny

script_dir=$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd) || deny
repo_root=$(cd -P -- "$script_dir/.." && pwd) || deny
roles_file=$repo_root/lib/codex-roles.txt
session_library=$repo_root/lib/codex-sessions-validate.sh
proof_library=$repo_root/hooks/lib/kimi-proof-state.sh
[[ -f $roles_file && ! -L $roles_file ]] || deny
[[ -f $session_library && ! -L $session_library ]] || deny
[[ -f $proof_library && ! -L $proof_library ]] || deny
# shellcheck source=../lib/codex-sessions-validate.sh
. "$session_library" || deny
# shellcheck source=lib/kimi-proof-state.sh
. "$proof_library" || deny

roles=()
mapfile -t roles <"$roles_file" || deny
((${#roles[@]} > 0)) || deny
role_pattern=
for role in "${roles[@]}"; do
  [[ $role =~ ^[A-Za-z0-9][A-Za-z0-9-]*$ ]] || deny
  role_pattern+=${role_pattern:+|}$role
done
cyber_pattern='^[0-9a-f]{64}$'
orchestration_pattern="^orchestration-($role_pattern)-[0-9a-f]{16}$"

input=$(cat) || deny
sid=$(jq -er '.session_id|select(type=="string")' <<<"$input") || deny
codex_session_id_is_valid "$sid" || deny
base=$(kimi_proof_root) || deny
dir=$base/$sid/cyber-escalation
[[ -d $dir && ! -L $base && ! -L $base/$sid && ! -L $dir ]] || deny

exec {dfd}<"$dir" || deny
flock -x "$dfd" || deny
now=$(date +%s) || deny
shopt -s nullglob

for marker_path in "$dir"/*; do
  [[ -f $marker_path && ! -L $marker_path ]] || continue
  marker_name=${marker_path##*/}
  [[ $marker_name =~ $cyber_pattern ||
     $marker_name =~ $orchestration_pattern ]] || continue
  IFS= read -r timestamp <"$marker_path" || timestamp=
  if [[ $timestamp =~ ^[0-9]+$ ]] &&
      ((timestamp <= now && now - timestamp <= 600)); then
    rm -- "$marker_path" 2>/dev/null && exit 0
  elif [[ $timestamp =~ ^[0-9]+$ ]] && ((now - timestamp > 600)); then
    rm -- "$marker_path" 2>/dev/null || :
  fi
done
deny
