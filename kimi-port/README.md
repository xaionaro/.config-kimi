# Kimi Port Status

Port of the hook/proof harness to Kimi Code. This file tracks what is
ported, what is verified, and what remains as known limitation.

## Hook wiring

- All hooks are wired via `config.toml` `[[hooks]]` entries (Kimi Code
  native). The legacy JSON hook manifest (`hooks.json`) was removed in
  the codex-legacy purge; tests assert the TOML wiring via a converted
  view (`hooks_config_json` in `hooks/tests/run.sh`).

## Naming policy

- Library files are `hooks/lib/kimi-*.sh`; public helpers use the
  `kimi_` prefix. No codex-specific legacy names remain in `hooks/`,
  `bin/`, `proofs/`, or `skills/agent-teams-execution/` (acceptance
  grep in the port manifest). Historical attributions stay in
  CREATION-LOG files only.

## Subagent hook exemptions (Edit gate + Stop gate)

Status: FIXED.

- Detection: `kimi_hook_is_subagent_context_wire` classifies a hook
  payload as subagent context when the session main wire holds an open
  `Agent`/`AgentSwarm` tool.call whose record age is in
  [3000 ms, 6 h] (floor kills the batched-spawn sibling race; ceiling
  rejects crash orphans). Wire protocol canary writes one
  `kimi-wire-warnings-<sid>.jsonl` line per kind and fails closed.
- Edit gate (`hooks/eci-active-gate.sh`): denies non-markdown
  Edit/Write on the main thread while the session ECI marker exists;
  spawned ECI/ATE agents are exempt. Evidence commits: ed85f2f
  (uutils-comm fail-open fix), 61bd4db (batch-race floor + protocol
  canary), ce75f27 (warning channel + 3000 ms floor).
- Stop gate (`hooks/stop-gate.sh`): blocks main-thread stops under
  ECI/ATE markers only while no delegated work is live
  (`kimi_session_has_active_work`: open Agent call age in [0, 6 h], or a
  running `tasks/*.json` entry within startedAt+timeoutMs+300 s).
  Subagent stops are never allowed or blocked by this exemption.
  Evidence commit: 18531f9 (turn-stop enforcement).
- Gate proofs (live, this deployment): an ECI implementer edited
  non-markdown files under the marker (allowed), a background-dispatched
  implementer was denied at the gate (fail-closed by design), a
  batched-race probe was blocked, and the 19-case unit matrix passes in
  `hooks/tests/run.sh`.

## Known limitations

- Background agents close their spawn call at dispatch (`status:
  running` result), so their edits read as main context at the Edit
  gate and are denied under a marker (fail-closed). ECI/ATE under a
  marker must use foreground agents. The Stop exemption covers them via
  `tasks/*.json`.
- Legacy cwd-matched ECI markers (`<reserved-dir>/eci_active` with a
  `cwd:` field) are still honored until the sessions that own the five
  live markers disengage; removal is deferred until then.
- The pre-reviewer worker is inert on kimi: its admission gate
  (`kimi_hook_transcript_first_record_is_admissible`) always fails on
  kimi payloads, which carry no transcript_path. Enablement is deferred;
  the worker and its transcript-based tests remain for the codex-format
  fixtures.

## Purge log (codex-legacy removal)

- Transcript family: `kimi_hook_transcript_first_record`,
  `kimi_hook_parent_session_id`, the `session_meta` branch of the
  subagent predicate, the stop-gate transcript-activity consumer
  (payload parse, `transcript_has_activity_since_last_user`, early-exit
  variable), `test_transcript_admission.py`, and all
  session_meta-driven stop/gate tests (rewired to wire fixtures where
  the behavior is still live).
- Alias/rollout shapes: `kimi_proof_alias_session_id`,
  `kimi_real_session_dir_name`, the alias branch and rollout case-arm of
  `kimi_path_owner_session_id` (default-root fallback retained).
- Legacy hook manifest: `hooks.json` (wiring lives in `config.toml`;
  all consumers repointed, jq-on-JSON assertions replaced by
  tomllib-on-TOML or the converted view).
- Stale backup: `hooks/lib/codex-proof-state.sh.bak-20260718`.
