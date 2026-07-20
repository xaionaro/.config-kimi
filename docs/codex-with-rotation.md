# Codex credential rotation

`codex-with-rotation` runs `codex exec --ephemeral --json` with a disposable,
private `CODEX_HOME`. It copies one credential into that home, classifies Codex
JSONL failures, and rotates only after a recognized quota signal.

## Invocation

```bash
printf '%s\n' 'the task prompt' |
  ~/.kimi-code/bin/codex-with-rotation --label implementer -- --sandbox workspace-write
```

`--label` is included in every classifier-emitted status JSON object for caller
correlation. It is not forwarded to Codex or included in `task_sig`. Everything
after `--` is passed literally after `codex exec --ephemeral --json`.

The wrapper captures stdin once in a mode-0600 spool under `~/tmp/`. Each of at
most three attempts receives the same bytes and literal argv. It reads and pins
the active account once at task start. Local-hook and cyber retries keep that
account even if another process changes global active state.

## State and credential isolation

The default state is `~/.codex/.auth-active` (mode 0600), serialized with
`~/.codex/.auth-active.lock`. On first use, the wrapper reads only
`tokens.account_id` from these files, in order, and deduplicates by account ID:

1. `~/.codex/auth.json`
2. `~/.codex/auth.json-danusya`
3. `~/.codex/auth.json-xaionaro`

Missing pool members are skipped. An empty pool is an internal failure. A
single distinct account may run normally, but a later rotation request exits
74 before changing accounts.

For each attempt, the wrapper creates a mode-0700 directory under `~/tmp/` and
makes real copies of the task's pinned credential, `config.toml`, `hooks/`, and
`plugins/` when present. Copied directories are mode 0700 and copied files are
mode 0600. Pool members are opened read-only and retain their original mode and
bytes. OAuth refresh writes made by Codex land only in the disposable copy and
are discarded.

State updates use an in-directory mode-0600 temporary file, `fsync`, and atomic
replacement while holding the exclusive lock. Reads that choose an account use
the shared lock. Quota rotation re-reads `active_account_id` under the exclusive
lock; if another process already moved it away from the failed ID, the stale
process records the failed account's cooldown but does not rotate again. A
quota decision is the only within-task operation that changes the pinned
account; its locked result supplies the next pinned pool entry directly.

Every state write drops cooldowns whose `until_utc` has passed and task streaks
whose `last_observed_utc` is more than 600 seconds old. Resetting a task removes
its entry instead of retaining a zero-count tombstone.

## Constant ownership

- `bin/codex-with-rotation` owns the readonly `MAX_ATTEMPTS` and `POOL_NAMES`
  Bash constants. It renders them into help and passes them to the classifier.
- `bin/codex-with-rotation-classify` owns state schema, cooldown/window lengths,
  classification variants, whole-stream priority, Guardian deny risk levels,
  and the 50-line
  diagnostic-tail bound as Python module constants.
- Pool filenames seed `.auth-active.pool` only when state is first created.
  Thereafter the locked state file is the account-order source of truth; changing
  `POOL_NAMES` requires an explicit state migration or reseed.

## Task signature

`task_sig` is a 64-character lowercase SHA-256 digest. Its input is defined by
the following byte operations, where `stdin_spool` contains all stdin and
`"$@"` is only the pass-through argv after `--`:

```bash
printf '%s:' "$(wc -c <stdin_spool)" >> hash_input
cat stdin_spool >> hash_input
printf '_%s:' "$#" >> hash_input
printf '%s' "$@" >> hash_input
sha256sum hash_input | cut -c1-64
```

Argument count is encoded, but individual argv lengths are not. This deliberately
matches the required definition; callers must treat the signature as a task
correlation key, not a cryptographic encoding of an unambiguous argv tuple.

## Classification and actions

Across the complete stdout event stream, classification precedence is
`local_hook_deny`, `cyber`, `quota`, then `unknown`, independent of arrival
order. Stderr is scanned first for the highest-priority local-hook substring.

The classifier reads stdout JSONL and stderr line-by-line through end of file.
Each parsed event is discarded immediately after its stateless classification;
only one first-seen variant per decisive class is retained. Separate
`deque(maxlen=50)` raw-line tails survive for an unknown-result diagnostic, so
classification memory does not grow with output length and the files are not
read again to produce tails.

| Class | Recognized variants | Action |
|---|---|---|
| `local_hook_deny` | `approval_denied`; denied `CommandExecutionApproval`; exact PreToolUse-block stderr text | Retry once on the pinned account; a second hit exits 73. |
| `cyber` | `CyberPolicyResponse`, `cyber_policy`, `HighRiskCyberActivity`, `high_risk_cyber_activity`; denying/blocking/rejecting guardian assessment; Guardian `risk_level` `high`, `critical`, or `severe` (case-insensitive) | First hit records a per-`task_sig` streak and retries the pinned account. A second hit within 600 seconds exits 75. Missing, empty, and other Guardian risk levels are not cyber signals by themselves. |
| `quota` | Usage/rate/session-budget/quota/not-included variants, or `codex_error_http_status_code` 429 | Cool the failed account for 600 seconds and advance in pool order, skipping active cooldowns. |
| `unknown` | Malformed, unmatched, or otherwise unclassified failure output | Fail closed with exit 76 and the last 50 stdout/stderr lines. |

Any non-cyber result resets that task's cyber streak. A cyber observation more
than 600 seconds after the stored observation starts a new streak.

Success requires Codex exit 0, no `turn.failed`/`error` event, and no malformed
JSONL line. On success, the wrapper forwards Codex stdout and emits one status
object on stderr.

## Exit contract

| Exit | Meaning |
|---:|---|
| 0 | Codex success; stdout forwarded. |
| 1 | Generic invocation/argument failure. |
| 70 | Three attempts were consumed without another terminal result. |
| 71 | Wrapper failure, missing required source material, or corrupt state. |
| 72 | Every alternative account is cooling down. |
| 73 | Repeated local-hook denial. |
| 74 | Rotation requested with fewer than two distinct accounts. |
| 75 | Cyber escalation, or `CODEX_KIMI_FORCE=1`. |
| 76 | Unknown failure; inspect raw tails after the stderr status JSON. |

Raw Codex exit codes never escape. The stderr JSON reports the true value in
`codex_exit`; wrapper-private exits 73–76 must not be reinterpreted as Codex
statuses.

On exit 71, the Bash trap moves the private run directory to
`${KIMI_PROOF_ROOT:-$HOME/.cache/kimi-proof}/$SESSION_ID/codex-with-rotation-failures/<timestamp>/`
with mode 0700 and prints the retained path. These diagnostics can contain copied
credentials and task input; `wrapper-error.log` records the internal causal
chain with mode 0600. If the move cannot be completed, the mode-0700 run
directory remains under `~/tmp/` and its path is printed instead. Inspect the
directory privately and remove it afterward.

## Environment

- `CODEX_KIMI_FORCE=1` initializes/validates state, does not launch Codex, emits
  `class=force_kimi`, and exits 75.
- `CODEX_ROTATE_STATE_DIR=<dir>` replaces `~/.codex` for state, lock, pool,
  config, hooks, and plugins. It is the isolated-test override requested by the
  implementation contract.
- An inherited `CODEX_HOME` does not select state or credentials. The wrapper
  replaces it for every child launch.

Direct `codex exec` against `~/.codex` is unsupported. It bypasses rotation and
allows Codex to write credential state outside the disposable home.

## Reseeding an expired refresh token

1. Create a mode-0700 throwaway directory under `~/tmp/`.
2. Run `CODEX_HOME=<throwaway> codex login`.
3. Copy the new `auth.json` to an in-directory, mode-0600 temporary file beside
   only the affected pool member.
4. Atomically rename that temporary file over the affected member, preserving
   the member's intended mode.
5. Remove the throwaway directory without printing or committing its contents.

The private launch home intentionally discards refresh writes, so manual reseed
is required after a refresh token expires.

## Enforcement-marker boundary

`codex-issue-marker` writes one-use, 600-second capability files consumed by
`codex-first-gate.sh`. Both resolve their root through `KIMI_PROOF_ROOT` with the
same default as `hooks/lib/kimi-proof-state.sh`. Approved orchestration roles
come only from `~/.kimi-code/lib/codex-roles.txt`.

Markers are session-scoped capability tokens, not task-bound authorizations; they defend against accidental Kimi-quota consumption, not against orchestrator bugs or hostile same-UID processes. An orchestrator that issues a marker for task A and then calls Agent for unrelated task B will consume the marker on B.

Delegated worker execution (code, research, and reviews) runs through
codex-via-Bash. Kimi orchestration primitives (`Agent`, `AgentSwarm`,
`TaskOutput`, and `TaskStop`) still manage ECI/ATE role lifecycle. The two
coexist: Codex performs delegated work while Kimi manages workflow state. An ECI
orchestrator can issue the `critic-step2` marker and spawn that role; the spawned
critic can then use codex-via-Bash for its analysis.

## Verification caveats

The real `codex-cli 0.144.6` hash/stat run is recorded in
[`codex-with-rotation-poc.md`](codex-with-rotation-poc.md). It completed on the
first attempt and reported identical before/after pool manifests.

- Live quota and cyber JSONL wire shapes remain unverified. Classification is
  covered by synthetic fixtures and fails closed on anything unmatched.
- Behavior is pinned to and tested with `codex-cli 0.144.6`. Re-run the fixture
  suite and a live probe after every Codex upgrade.
- Wrapper-private exit meanings are a local protocol and are not Codex API
  guarantees.

## Implementation-spec clarifications

- The spec once calls the signature helper `sha1_of_length_prefixed_tuple`, but
  its exact definition, output width, and help requirement all require SHA-256.
  The implementation follows that exact SHA-256 definition.
- Linux rejects `exec {fd}>"$dir"` for a directory. `codex-issue-marker` opens
  the directory read-only (`exec {fd}<"$dir"`) before `flock`, matching the
  supplied gate and preserving the intended serialization.
- `CODEX_ROTATE_STATE_DIR` was added for the mandated fake-pool tests. It
  redirects the complete state/source home so no real credential is consulted.
