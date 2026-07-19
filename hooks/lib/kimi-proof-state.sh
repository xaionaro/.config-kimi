#!/usr/bin/env bash
# Shared state helpers for Kimi proof-adjacent hooks.

kimi_proof_root() {
  printf '%s\n' "${KIMI_PROOF_ROOT:-$HOME/.cache/kimi-proof}"
}

kimi_valid_session_id() {
  case "${1:-}" in
    ""|*[!A-Za-z0-9_-]*) return 1 ;;
    *) return 0 ;;
  esac
}

# Reserved proof-root entries: bare names are fixed state directories;
# *-suffixed globs are per-session file families that must never be read
# as session directories.
kimi_reserved_proof_dir() {
  case "${1:-}" in
    activity|audit|eci|history|pre-reviewer|reviewer|reviewer-dumps|security-warnings-*|kimi-wire-warnings-*|side-stop|skip-stop|skills)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

kimi_canonical_cwd() {
  local cwd="${1:-$PWD}"
  if [ -d "$cwd" ]; then
    (cd "$cwd" 2>/dev/null && pwd -P) || printf '%s\n' "$cwd"
  else
    printf '%s\n' "$cwd"
  fi
}

kimi_resolve_hook_path() {
  local cwd="${1:-$PWD}"
  local path="${2:-}"

  [ -n "$path" ] || return 1
  [ -n "$cwd" ] || cwd="$PWD"
  case "$path" in
    "~") path="$HOME" ;;
    "~/"*) path="$HOME/${path#~/}" ;;
  esac
  case "$path" in
    /*) ;;
    *) path="$cwd/$path" ;;
  esac

  realpath -m -- "$path" 2>/dev/null || printf '%s\n' "$path"
}

kimi_session_ledger_basenames() {
  printf '%s\n' \
    "project-understanding.md" \
    "high_level_log.md" \
    "latest-status-report.md"
}

kimi_session_ledger_basename() {
  case "${1:-}" in
    project-understanding.md|high_level_log.md|latest-status-report.md)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

kimi_path_is_session_ledger_file() {
  local path="$1"
  local actual_root default_root root rest sid filename

  [ -n "$path" ] || return 1
  filename="${path##*/}"
  kimi_session_ledger_basename "$filename" || return 1

  actual_root="$(kimi_resolve_hook_path "$PWD" "$(kimi_proof_root)" 2>/dev/null || kimi_proof_root)"
  default_root="$(kimi_resolve_hook_path "$PWD" "$HOME/.cache/kimi-proof" 2>/dev/null || printf '%s\n' "$HOME/.cache/kimi-proof")"
  for root in "$actual_root" "$default_root"; do
    [ -n "$root" ] || continue
    case "$path" in
      "$root"/*)
        rest="${path#"$root"/}"
        sid="${rest%%/*}"
        [ "$rest" != "$sid" ] || continue
        [ "${rest#*/}" = "$filename" ] || continue
        kimi_reserved_proof_dir "$sid" && continue
        kimi_valid_session_id "$sid" || continue
        return 0
        ;;
    esac
  done

  return 1
}

kimi_hash_string() {
  if command -v sha256sum >/dev/null 2>&1; then
    printf '%s' "${1:-}" | sha256sum | awk '{print $1}'
  elif command -v python3 >/dev/null 2>&1; then
    printf '%s' "${1:-}" | python3 -c \
      'import hashlib, sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())'
  else
    return 1
  fi
}

kimi_cwd_key() {
  local cwd
  cwd="$(kimi_canonical_cwd "${1:-$PWD}")"
  kimi_hash_string "$cwd"
}

kimi_session_state_dir() {
  local kind="$1"
  local session_id="$2"
  kimi_valid_session_id "$session_id" || return 1
  printf '%s/%s/sessions/%s\n' "$(kimi_proof_root)" "$kind" "$session_id"
}

kimi_cwd_state_dir() {
  local kind="$1"
  local cwd="${2:-$PWD}"
  printf '%s/%s/cwd/%s\n' "$(kimi_proof_root)" "$kind" "$(kimi_cwd_key "$cwd")"
}

kimi_ensure_cwd_state_dir() {
  local kind="$1"
  local cwd="${2:-$PWD}"
  local dir
  dir="$(kimi_cwd_state_dir "$kind" "$cwd")" || return 1
  mkdir -p "$dir" || return 1
  kimi_canonical_cwd "$cwd" >"$dir/cwd"
  printf '%s\n' "$dir"
}

kimi_cli_state_dir() {
  local kind="$1"
  local create="${2:-false}"
  local dir

  if [ -n "${KIMI_SESSION_ID:-}" ]; then
    dir="$(kimi_session_state_dir "$kind" "$KIMI_SESSION_ID")" || return 1
    [ "$create" = "true" ] && mkdir -p "$dir"
    printf '%s\n' "$dir"
    return 0
  fi

  if [ "$create" = "true" ]; then
    kimi_ensure_cwd_state_dir "$kind" "$PWD"
  else
    kimi_cwd_state_dir "$kind" "$PWD"
  fi
}

kimi_cli_state_file() {
  local kind="$1"
  local filename="$2"
  local create="${3:-false}"
  local dir
  dir="$(kimi_cli_state_dir "$kind" "$create")" || return 1
  printf '%s/%s\n' "$dir" "$filename"
}

kimi_existing_state_file() {
  local kind="$1"
  local filename="$2"
  local session_id="${3:-}"
  local cwd="${4:-}"
  local dir path

  if kimi_valid_session_id "$session_id"; then
    dir="$(kimi_session_state_dir "$kind" "$session_id")" || return 1
    path="$dir/$filename"
    [ -f "$path" ] && { printf '%s\n' "$path"; return 0; }
  fi

  if [ -n "$cwd" ]; then
    dir="$(kimi_cwd_state_dir "$kind" "$cwd")" || return 1
    path="$dir/$filename"
    [ -f "$path" ] && { printf '%s\n' "$path"; return 0; }
  fi

  if kimi_valid_session_id "$session_id"; then
    path="$(kimi_proof_root)/$session_id/$filename"
    [ -f "$path" ] && { printf '%s\n' "$path"; return 0; }
  fi

  return 1
}

kimi_state_session_id() {
  local file="$1"
  awk -F':[[:space:]]*' '$1 == "session_id" { print $2; exit }' "$file" 2>/dev/null
}

kimi_note_state_session_id() {
  local file="$1"
  local session_id="$2"
  local existing

  kimi_valid_session_id "$session_id" || return 0
  [ -f "$file" ] || return 0
  existing="$(kimi_state_session_id "$file" || true)"
  [ -n "$existing" ] && return 0
  printf 'session_id: %s\n' "$session_id" >>"$file"
}

kimi_mark_activity() {
  local session_id="$1"
  local cwd="$2"
  local marker_name="$3"
  local dir marker

  kimi_valid_session_id "$session_id" || return 0
  case "$marker_name" in
    shell|edit|subagent) ;;
    *) return 0 ;;
  esac

  dir="$(kimi_session_state_dir activity "$session_id")" || return 0
  mkdir -p "$dir" || return 0
  marker="$dir/$marker_name"
  {
    printf 'kind: %s\n' "$marker_name"
    [ -n "$cwd" ] && printf 'cwd: %s\n' "$cwd"
    date -u '+created_utc: %Y-%m-%dT%H:%M:%SZ'
  } >"$marker"
}

kimi_git_repo_root_for_path() {
  local cwd="${1:-$PWD}"
  local path="${2:-}"
  local target dir repo

  if [ -n "$path" ]; then
    case "$path" in
      /*) target="$path" ;;
      *) target="$cwd/$path" ;;
    esac
  else
    target="$cwd"
  fi

  if [ -d "$target" ]; then
    dir="$target"
  else
    dir="$(dirname -- "$target")"
  fi
  while [ ! -d "$dir" ] && [ "$dir" != "/" ]; do
    dir="$(dirname -- "$dir")"
  done
  [ -d "$dir" ] || return 1

  repo="$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null || true)"
  [ -n "$repo" ] || return 1
  kimi_canonical_cwd "$repo"
}

kimi_repo_relative_file_path() {
  local repo="$1"
  local cwd="${2:-$PWD}"
  local path="${3:-}"
  local target rel

  [ -n "$repo" ] && [ -n "$path" ] || return 1
  case "$path" in
    /*) target="$path" ;;
    *) target="$cwd/$path" ;;
  esac

  [ ! -d "$target" ] || return 1
  rel="$(realpath -m --relative-to="$repo" "$target" 2>/dev/null || true)"
  [ -n "$rel" ] || return 1
  case "$rel" in
    "."|".."|../*|/*) return 1 ;;
  esac
  printf '%s\n' "$rel"
}

kimi_note_touched_repo() {
  local session_id="$1"
  local cwd="${2:-$PWD}"
  local path="${3:-}"
  local repo dir marker key head status status_sha tmp rel_path

  kimi_valid_session_id "$session_id" || return 0
  repo="$(kimi_git_repo_root_for_path "$cwd" "$path" 2>/dev/null || true)"
  [ -n "$repo" ] || return 0
  rel_path="$(kimi_repo_relative_file_path "$repo" "$cwd" "$path" 2>/dev/null || true)"

  dir="$(kimi_session_state_dir touched-repos "$session_id")" || return 0
  mkdir -p "$dir" || return 0
  key="$(kimi_cwd_key "$repo")"
  marker="$dir/$key"
  if [ -f "$marker" ]; then
    if [ -n "$rel_path" ]; then
      grep -Fxq -- "path: $rel_path" "$marker" 2>/dev/null || printf 'path: %s\n' "$rel_path" >>"$marker"
    else
      grep -Fxq 'repo_wide: true' "$marker" 2>/dev/null || printf 'repo_wide: true\n' >>"$marker"
    fi
    return 0
  fi

  head="$(git -C "$repo" rev-parse HEAD 2>/dev/null || true)"
  status="$(git -C "$repo" status --porcelain=v1 --untracked-files=normal 2>/dev/null || true)"
  status_sha="$(kimi_hash_string "$status")"
  tmp="$marker.tmp.$$"
  {
    printf 'repo: %s\n' "$repo"
    printf 'head: %s\n' "$head"
    printf 'status_sha: %s\n' "$status_sha"
    if [ -n "$rel_path" ]; then
      printf 'path: %s\n' "$rel_path"
    else
      printf 'repo_wide: true\n'
    fi
    date -u '+created_utc: %Y-%m-%dT%H:%M:%SZ'
  } >"$tmp" && mv "$tmp" "$marker"
}

kimi_state_value() {
  local file="$1"
  local key="$2"
  awk -F':[[:space:]]*' -v key="$key" '$1 == key { print $2; exit }' "$file" 2>/dev/null
}

kimi_legacy_eci_markers_for_cwd() {
  local cwd="${1:-}"
  local root marker dir name marker_cwd canonical_cwd canonical_marker_cwd found=false

  [ -n "$cwd" ] || return 1
  root="$(kimi_proof_root)"
  [ -d "$root" ] || return 1
  canonical_cwd="$(kimi_canonical_cwd "$cwd")"

  shopt -s nullglob
  for marker in "$root"/*/eci_active; do
    [ -f "$marker" ] || continue
    dir="${marker%/*}"
    name="${dir##*/}"
    kimi_reserved_proof_dir "$name" || continue
    marker_cwd="$(kimi_state_value "$marker" cwd || true)"
    [ -n "$marker_cwd" ] || continue
    canonical_marker_cwd="$(kimi_canonical_cwd "$marker_cwd")"
    [ "$canonical_marker_cwd" = "$canonical_cwd" ] || continue
    printf '%s\n' "$marker"
    found=true
  done
  shopt -u nullglob

  [ "$found" = true ]
}

kimi_side_stop_applies_to_session() {
  local file="$1"
  local session_id="$2"
  local command parent_session_id

  [ -f "$file" ] || return 1
  command="$(kimi_state_value "$file" command || true)"
  [ "$command" = "/side" ] || return 1

  parent_session_id="$(kimi_state_value "$file" parent_session_id || true)"
  if kimi_valid_session_id "$parent_session_id"; then
    [ "$parent_session_id" != "$session_id" ]
    return
  fi

  return 0
}

kimi_state_file_is_session_scoped() {
  local kind="$1"
  local filename="$2"
  local session_id="$3"
  local file="$4"
  local expected

  expected="$(kimi_session_state_dir "$kind" "$session_id" 2>/dev/null || true)"
  [ -n "$expected" ] && [ "$file" = "$expected/$filename" ]
}

kimi_side_stop_is_active_for_session() {
  local file="$1"
  local session_id="$2"

  [ -n "$file" ] && [ -f "$file" ] || return 1
  kimi_side_stop_applies_to_session "$file" "$session_id" || return 1

  if kimi_state_file_is_session_scoped side-stop side_stop "$session_id" "$file"; then
    return 0
  fi

  [ -n "$(find "$file" -mmin -60 -print 2>/dev/null)" ]
}

kimi_bind_side_stop_to_session() {
  local file="$1"
  local session_id="$2"
  local dir

  [ -f "$file" ] || return 1
  dir="$(kimi_session_state_dir side-stop "$session_id")" || return 1
  mkdir -p "$dir" || return 1
  cp "$file" "$dir/side_stop"
}

kimi_hook_is_subagent_context() {
  local input="${1:-}"

  kimi_hook_is_subagent_context_wire "$input"
}

# Kimi-native subagent detection. Kimi hook payloads carry no transcript_path
# and no agent identity; main and subagent calls share one session_id, and the
# caller's own tool.call record is appended to its wire only after PreToolUse
# hooks complete (verified 2026-07-18: 8/8 captured fires across 4 sessions
# had no wire record yet). Context is identified by the main wire's open
# Agent/AgentSwarm calls and their age:
#  - A foreground spawned agent holds an open tool.call (no tool.result) in
#    agents/main/wire.jsonl for its entire run; main, blocked inside it,
#    cannot emit further calls — except batched with the spawn: a batched
#    [Agent, X...] step fires each sibling X's hook with the Agent call open
#    (session_a3d9d20a lines 940-941: Agent t=1784403893266, Write
#    t=1784403893953, same stepUuid, 687 ms gap).
#  - Sibling hook delay is the batch's cumulative hook latency, visible as
#    tool.call record gaps: 76 batched [Agent+X] steps across the session
#    corpus, max observed gap 1517 ms (session_dcf3436c step 5aabe8bd:
#    Agent t=1784406871828, Write t=1784406873345, Agent open 213.9 s; a
#    second >1 s instance in session_a3d9d20a, 1114 ms). A real foreground
#    subagent's first tool fires seconds after spawn: min
#    wire-creation-to-first-tool-call 5095 ms (n=17 agent wires,
#    session_a3d9d20a); min nonzero ttftMs 2856 ms (n=500, its log). The
#    3000 ms floor separates the two shapes with ~1.5 s headroom over the
#    observed batched max and ~2.1 s under the observed spawn min; both
#    samples are small and single-deployment. Residual (fail-open): a
#    batched sibling whose cumulative hook delay exceeds 3000 ms is
#    classified subagent — batch-scoped: every sibling tool of that step
#    is exempted; the observed tail grows with batch size x hook latency.
#  - The 6 h ceiling is ≈4.5x the longest observed completed foreground run
#    (79.6 min, session_da1b7d20; corpus n≈272 call→result pairs after
#    dropping background spawn-acks, resume-synthesized interruption
#    results, and one instant already-running spawn error). Pure
#    defense-in-depth for crash orphans on unknown-resume-behavior kimi
#    versions; a misfire fails closed (deny). Session resume synthesizes
#    interruption results for crash orphans (session_d56600db), so a live
#    session cannot legitimately hold one.
#  - Stop-hook assumption: no real subagent Stop fires <3 s after spawn
#    (corpus min spawn→loop-end 5766 ms, a provider-error run; min
#    completed 20409 ms; ttftMs min 2856 ms makes a sub-3 s Stop
#    implausible; the only sub-2 s call→result is an instant
#    "already running and cannot run concurrently" spawn error with no
#    agent loop, hence no Stop hook). If one ever occurs it classifies as
#    main in this window, and the Stop gate's active-work exemption
#    (kimi_session_has_active_work: open call age <6 h, no
#    floor) then continues the stop under own and legacy markers alike
#    instead of blocking it; genuine subagent stops are unaffected
#    because the subagent branch never consults the exemption. No
#    spin-to-timeout and no deny-forever path arises from the floor.
# Background agents close their call record at spawn ("status: running"
# result), so their edits classify as main (denied under a marker): a
# documented fail-closed limitation; ECI/ATE under a marker must use
# foreground agents. Missing or unparseable signals return main-context
# (return 1), keeping deny-gates fail-closed. Matching is textual: a
# non-Agent call whose raw args embed the literal "name":"Agent" substring
# also contributes its toolCallId; the false positive is benign and
# self-corrects when that call's own tool.result lands. A main edit
# batched behind such a call is exempted only if cumulative hook latency
# pushes its hook past the 3000 ms floor; no such wire observed.
# Millisecond bounds for the open-call/task age scans below.
KIMI_WIRE_OPEN_CALL_FLOOR_MS=3000
KIMI_WIRE_OPEN_CALL_CEILING_MS=21600000
KIMI_TASK_DEFAULT_TIMEOUT_MS=10800000
KIMI_TASK_DEADLINE_GRACE_MS=300000

kimi_session_dir_for_id() {
  local sid="$1" root="${KIMI_CODE_HOME:-$HOME/.kimi-code}/sessions" d
  kimi_valid_session_id "$sid" || return 1
  for d in "$root"/*/"$sid"; do
    [ -d "$d" ] || continue
    printf '%s\n' "$d"
    return 0
  done
  return 1
}

kimi_wire_security_warning() {
  local sid="$1" kind="$2" file
  kimi_valid_session_id "$sid" || return 0
  mkdir -p "$(kimi_proof_root)" 2>/dev/null || true
  file="$(kimi_proof_root)/kimi-wire-warnings-$sid.jsonl"
  if [ -f "$file" ] && grep -qF "\"$kind\"" "$file" 2>/dev/null; then
    return 0
  fi
  printf '{"kind":"%s","session_id":"%s","utc":"%s"}\n' \
    "$kind" "$sid" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" >>"$file" 2>/dev/null || true
}

# Shared open-Agent/AgentSwarm-call scan: returns 0 when the wire holds an
# open tool.call (no tool.result) whose record age is in [floor_ms,
# KIMI_WIRE_OPEN_CALL_CEILING_MS]; anything unparseable yields no match.
kimi_wire_open_call_age() {
  local wire="$1" floor_ms="$2" now_ms="$3"
  # substr offsets: len('"toolCallId":"')=14 (+1 closing quote=15); len('"time":')=7 (+1 trailing brace=8).
  awk -v now="$now_ms" -v floor="$floor_ms" -v ceil="$KIMI_WIRE_OPEN_CALL_CEILING_MS" '
    index($0, "\"event\":{\"type\":\"tool.call\"") &&
      (index($0, "\"name\":\"Agent\"") || index($0, "\"name\":\"AgentSwarm\"")) {
      id = ""; t = ""
      if (match($0, /"toolCallId":"[^"]+"/))
        id = substr($0, RSTART + 14, RLENGTH - 15)
      if (match($0, /"time":[0-9]+}[[:space:]]*$/))
        t = substr($0, RSTART + 7, RLENGTH - 8)
      if (id != "") open[id] = t
      next
    }
    index($0, "\"event\":{\"type\":\"tool.result\"") {
      if (match($0, /"toolCallId":"[^"]+"/))
        delete open[substr($0, RSTART + 14, RLENGTH - 15)]
      next
    }
    END {
      found = 0
      for (id in open) {
        if (open[id] == "") continue          # no record time → fail closed
        age = now - open[id]
        if (age >= floor && age <= ceil) { found = 1; break }
      }
      exit(found ? 0 : 1)
    }
  ' "$wire"
}

kimi_hook_is_subagent_context_wire() {
  local input="${1:-}" sid session_dir wire now_ms

  sid=$(printf '%s' "$input" | jq -r '.session_id // empty' 2>/dev/null) || return 1
  [ -n "$sid" ] || return 1
  session_dir=$(kimi_session_dir_for_id "$sid") || return 1
  wire="$session_dir/agents/main/wire.jsonl"
  [ -f "$wire" ] || return 1

  # Format canary: unknown wire protocol → fail closed + warn once per kind.
  if ! head -n 1 "$wire" 2>/dev/null | grep -qF '"protocol_version":"1.4"'; then
    kimi_wire_security_warning "$sid" "wire-protocol-mismatch"
    return 1
  fi

  now_ms=$(( $(date +%s%N) / 1000000 ))
  kimi_wire_open_call_age "$wire" "$KIMI_WIRE_OPEN_CALL_FLOOR_MS" "$now_ms"
}

# Active-work exemption for Stop: returns 0 when the session's main wire or
# task state shows delegated work still live — an open Agent/AgentSwarm
# tool.call of any age up to 6 h (a foreground subagent holds its call open
# for its whole run; main cannot reach Stop while blocked inside it, so an
# open record at Stop time means the turn ended around an active subagent),
# or a background task whose tasks/<id>.json still says "running" before its
# startedAt+timeoutMs deadline plus KIMI_TASK_DEADLINE_GRACE_MS (300 s) of
# grace, or startedAt+KIMI_TASK_DEFAULT_TIMEOUT_MS (3 h) when the task
# declares no timeout. The ECI Stop gate reaches this helper only in main
# context, where the classification floor bounds the effective window to
# [0, 3000 ms): a main stop that fresh with an open call is the designed
# turn-ends-around-a-live-agent case. Any signal failure returns 1 (no
# active work), keeping deny-gates fail-closed.
kimi_session_has_active_work() {
  local input="${1:-}" sid session_dir wire now_ms
  local task_json status started timeout deadline
  sid=$(printf '%s' "$input" | jq -r '.session_id // empty' 2>/dev/null) || return 1
  [ -n "$sid" ] || return 1
  session_dir=$(kimi_session_dir_for_id "$sid") || return 1
  now_ms=$(( $(date +%s%N) / 1000000 ))

  # Background half: detached tasks (agents and bash) via tasks/*.json.
  for task_json in "$session_dir"/agents/main/tasks/*.json; do
    [ -f "$task_json" ] || continue
    status=$(jq -r '.status // empty' "$task_json" 2>/dev/null) || continue
    [ "$status" = "running" ] || continue
    started=$(jq -r '.startedAt // 0' "$task_json" 2>/dev/null || printf '0')
    timeout=$(jq -r '.timeoutMs // 0' "$task_json" 2>/dev/null || printf '0')
    case "$started$timeout" in *[!0-9]*|"") continue ;; esac
    [ "$started" -gt 0 ] 2>/dev/null || continue
    if [ "$timeout" -gt 0 ] 2>/dev/null; then
      deadline=$(( started + timeout + KIMI_TASK_DEADLINE_GRACE_MS ))
    else
      deadline=$(( started + KIMI_TASK_DEFAULT_TIMEOUT_MS ))
    fi
    [ "$now_ms" -lt "$deadline" ] && return 0
  done

  # Foreground half: open Agent/AgentSwarm call, age in [0, 6 h] (floor 0 —
  # Stop is not a batched sibling hook, so the 3000 ms classification floor
  # does not apply here).
  wire="$session_dir/agents/main/wire.jsonl"
  [ -f "$wire" ] || return 1
  head -n 1 "$wire" 2>/dev/null | grep -qF '"protocol_version":"1.4"' || return 1
  kimi_wire_open_call_age "$wire" 0 "$now_ms"
}

# Pre-reviewer worker admission gate: admits payloads whose transcript is
# readable. Kimi payloads carry no transcript_path, so this always fails
# for them and the pre-reviewer worker stays inert on kimi; enablement is
# deferred (see kimi-port/README.md).
kimi_hook_transcript_first_record_is_admissible() {
  local input="${1:-}"

  printf '%s' "$input" | \
    python3 "${BASH_SOURCE[0]%/*}/bounded_hook_input.py" \
      hook-transcript-first-record "${KIMI_CODE_HOME:-$HOME/.kimi-code}/sessions" \
      >/dev/null 2>&1
}

kimi_path_owner_session_id() {
  local path="$1"
  local root default_root rest sid

  [ -n "$path" ] || return 1

  root="$(kimi_proof_root)"
  default_root="$HOME/.cache/kimi-proof"
  for root in "$root" "$default_root"; do
    [ -n "$root" ] || continue
    case "$path" in
      "$root"/*)
        rest="${path#"$root"/}"
        sid="${rest%%/*}"
        kimi_reserved_proof_dir "$sid" && return 1
        kimi_valid_session_id "$sid" || return 1
        printf '%s\n' "$sid"
        return 0
        ;;
    esac
  done

  return 1
}

kimi_hook_allowed_session_ids() {
  local input="$1"
  local session_id

  session_id="$(printf '%s' "$input" | jq -r '.session_id // empty' 2>/dev/null || true)"
  if kimi_valid_session_id "$session_id"; then
    printf '%s\n' "$session_id"
  fi
}

kimi_session_owner_allowed() {
  local owner="$1"
  local allowed
  shift

  for allowed in "$@"; do
    [ "$owner" = "$allowed" ] && return 0
  done
  return 1
}

kimi_remove_session_state_file() {
  local kind="$1"
  local filename="$2"
  local session_id="$3"
  local dir
  dir="$(kimi_session_state_dir "$kind" "$session_id")" || return 0
  rm -f "$dir/$filename"
}

kimi_remove_cwd_state_file() {
  local kind="$1"
  local filename="$2"
  local cwd="${3:-$PWD}"
  local dir
  dir="$(kimi_cwd_state_dir "$kind" "$cwd")" || return 0
  rm -f "$dir/$filename"
}

kimi_markdown_section_has_body() {
  local file="$1"
  local target="$2"

  awk -v target="$target" '
    BEGIN { target = tolower(target) }
    function trim(s) {
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", s)
      return s
    }
    /^##[[:space:]]*/ {
      heading = $0
      sub(/^##[[:space:]]*/, "", heading)
      heading = tolower(trim(heading))
      if (in_section) exit
      if (heading == target) {
        in_section = 1
        next
      }
    }
    in_section {
      line = trim($0)
      if (line != "") found = 1
    }
    END { exit(found ? 0 : 1) }
  ' "$file"
}

kimi_eci_terminal_verdict_error() {
  local subject="$1"
  local file="$2"
  local counts accepted retired

  counts="$(awk '
    {
      line = tolower($0)
      scan = line
      while (match(scan, /(^|[^[:alnum:]_-])(clean-pass|user-closed):/)) {
        accepted++
        scan = substr(scan, RSTART + RLENGTH)
      }
      scan = line
      while (match(scan, /(^|[^[:alnum:]_-])hard-escalation:/)) {
        retired++
        scan = substr(scan, RSTART + RLENGTH)
      }
    }
    END { print accepted + 0, retired + 0 }
  ' "$file")"
  read -r accepted retired <<EOF
$counts
EOF

  if [ "${retired:-0}" -ne 0 ]; then
    printf '%s must include exactly one terminal verdict marker: clean-pass: or user-closed:, and must not include retired marker hard-escalation:. Report a blocker requiring user input while ECI remains active.\n' "$subject"
  elif [ "${accepted:-0}" -ne 1 ]; then
    printf '%s must include exactly one terminal verdict marker: clean-pass: or user-closed:.\n' "$subject"
  fi
}
