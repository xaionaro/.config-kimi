#!/usr/bin/env bash
# SessionStart hook: save git HEAD as the stop-hook baseline.

set -euo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HOOK_DIR/lib/kimi-proof-state.sh"
. "$HOOK_DIR/lib/kimi-tmp.sh"
kimi_init_tmp || true
kimi_install_fail_open_trap session-snapshot

input=$(cat)
session_id=$(printf '%s' "$input" | jq -r '.session_id // empty' 2>/dev/null || true)
transcript_path=$(printf '%s' "$input" | jq -r 'if (.transcript_path? | type) == "string" then .transcript_path else "" end' 2>/dev/null || true)
cwd=$(printf '%s' "$input" | jq -r 'if (.cwd? | type) == "string" then .cwd else "" end' 2>/dev/null || true)
[ -z "$cwd" ] && cwd="$PWD"

# Kimi SessionStart payloads do not distinguish ephemeral side threads via a
# legacy transcript_path, so the snapshot runs for every session start;
# without a transcript the subagent/side signals below stay at their fail-safe
# defaults.

case "$session_id" in
  ""|*[!A-Za-z0-9_-]*) exit 0 ;;
esac

root="$(kimi_proof_root)"
side_stop=$(kimi_existing_state_file side-stop side_stop "$session_id" "$cwd" 2>/dev/null || true)
if kimi_side_stop_is_active_for_session "$side_stop" "$session_id"; then
  kimi_bind_side_stop_to_session "$side_stop" "$session_id" || true
  exit 0
fi

proof_dir="$root/$session_id"
baseline="$proof_dir/baseline_head"

mkdir -p "$proof_dir"

if [ ! -f "$baseline" ]; then
  git rev-parse HEAD >"$baseline" 2>/dev/null || true
fi

rm -f "$proof_dir/skip_stop"

prune_marker_dirs() {
  local state_root="$1"
  local marker_name="$2"
  local dir marker

  [ -d "$state_root" ] || return 0
  find "$state_root" -mindepth 1 -maxdepth 1 -type d -mtime +30 -print 2>/dev/null |
    while IFS= read -r dir; do
      marker="$dir/$marker_name"
      if [ -f "$marker" ]; then
        case "$marker_name" in
          eci_active) continue ;;
          skip_stop)
            [ -n "$(find "$marker" -mmin -60 -print 2>/dev/null)" ] && continue
            ;;
        esac
      fi
      rm -rf "$dir"
    done
}

find "$root" -mindepth 1 -maxdepth 1 -type d \( -name '019*' -o -name 'session_*' \) -mtime +30 -print 2>/dev/null |
  while IFS= read -r dir; do
    [ -f "$dir/eci_active" ] && continue
    rm -rf "$dir"
  done || true
find "$root/history" -mindepth 1 -maxdepth 1 -type f -mtime +30 -delete 2>/dev/null || true
for state_root in skills audit reviewer reviewer-dumps; do
  find "$root/$state_root" -mindepth 1 -maxdepth 1 -mtime +30 -exec rm -rf {} + 2>/dev/null || true
done
find "$root/touched-repos/sessions" -mindepth 1 -maxdepth 1 -type d -mtime +30 -exec rm -rf {} + 2>/dev/null || true
prune_marker_dirs "$root/eci/sessions" eci_active
prune_marker_dirs "$root/eci/cwd" eci_active
prune_marker_dirs "$root/skip-stop/sessions" skip_stop
prune_marker_dirs "$root/skip-stop/cwd" skip_stop
prune_marker_dirs "$root/side-stop/sessions" side_stop

jq -n --arg ctx 'Load ~/.kimi-code/AGENTS.md and matching ~/.kimi-code/skills when applicable.' '{
  hookSpecificOutput: {
    hookEventName: "SessionStart",
    additionalContext: $ctx
  }
}'
