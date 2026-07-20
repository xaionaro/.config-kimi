---
name: explore-critique-implement
description: Use when Kimi selects ECI as the outer workflow or active ATE routes bounded work through ECI
---

# Explore-Critique-Implement

Separate the hand that builds from the hand that tears down. The builder cannot credibly critique its own output.

## When to use

| Use | Skip |
|-----|------|
| Solution space uncertain | Mechanical change with obvious answer and no future behavior risk |
| 2+ plausible approaches | Trivial typo or reformat |
| Correctness is load-bearing | Throwaway experiment |
| Research would reduce uncertainty | Mechanical rename |

**Triviality rule:** Classify by decision complexity and future behavior risk, not diff size, line count, file count, or locality. A single-line or single-file change is non-trivial when it changes instructions, prompts, routing, protocols, public contracts, security, persistence, concurrency, architecture, or reviewer/agent behavior, or when 2+ plausible approaches exist. Skip ECI only when the correct change is mechanical and consequences are obvious, directly verifiable, and carry no future behavior or routing risk.

Maintain a project-understanding ledger for every ECI run. Use the `maintaining-context-ledger` skill for storage path, content schema, update timing, and validity rules.

## Kimi adapter

- Start ECI only when Kimi selects it as the outer workflow or active ATE routes bounded work through it. Loading this skill alone does not start ECI.
- ECI includes its required spawned agents.
- A request to use ATE while ECI is active, or to cancel, withdraw, or replace ECI's root scope, is closure intent governed only by **Goal-backed user closure** below. Intent alone is not a completed `user-closed:` teardown.
- Run dependent agent work in the foreground: spawn with `Agent` and `subagent_type`, or follow up with `Agent` and `resume`, while omitting `run_in_background`. The foreground call returns the result directly.
- Use background `Agent` only for independent work. Rely on its automatic completion notification; use `TaskOutput(block=false)` only for a deliberate nonblocking snapshot.
- Use `TaskStop` only with the exact task ID of a known running background task that genuinely must be cancelled. Never use it to stop a foreground or completed agent, clear context, or perform generic teardown.
- Kimi ECI uses standard agent management tools only. Do not launch shell-wrapped Kimi agents. If the `Agent` tool or related agent tools are unavailable, ECI cannot run; hard-escalate to the user.
- The orchestrator never launches or waits for a Codex shell process directly. Spawn a bounded `codex-runner` subagent (`coder` or `explore` type) that invokes Codex through `~/.kimi-code/bin/codex-with-rotation`; keep it foreground when its result gates the next step. Raw `codex` invocation on the main thread is forbidden.

## Root goal

ECI does not itself enter goal mode. Call `CreateGoal` only when the user explicitly asks to start a goal or work autonomously toward an outcome, or a host goal-intake prompt asks for one. ECI selection alone is insufficient.

Call `GetGoal` before arming the edit gate.
- No current goal and the predicate holds: call `CreateGoal` with the root objective and completion criterion "Every active root-scope requirement is satisfied; each in-scope change passed its ECI acceptance route; required commits and clean-pass teardown completed."
- No current goal and the predicate does not hold: run ECI without creating a goal.
- Matching active goal: reuse it without calling `UpdateGoal`.
- Matching paused or blocked goal: call `UpdateGoal(status: "active")` only when the latest user instruction explicitly resumes that goal.
- Different visible goal: do not mutate it or use `replace: true`; follow **Goal-backed user closure**.
- Nested ECI under ATE never creates or replaces a goal; workflow handoff follows **Goal-backed user closure**.

`UpdateGoal(status: "complete")` is never part of **Goal-preserving clean pass**; a `clean-pass:` certificate closes only ECI. Budget exhaustion or partial work is not completion. For `blocked`, use the **Goal anti-loop** rule everywhere: call it immediately only for an impossible, unsafe, or contradictory objective; otherwise call it only after the same genuine impasse remains for three consecutive goal turns. Hard escalation follows the terminal rule below.

Note: The `eci_active` marker file is currently used by `stop-gate.sh` for continuation enforcement. Full migration to goal-driven continuation requires updating hooks (`stop-gate.sh`, `prompt-task-reminder.sh`, `session-snapshot.sh`) — this is documented follow-up work. The rules above define the target behavior; until hooks are migrated, both mechanisms coexist.

### Goal-preserving clean pass

A `clean-pass:` certificate closes ECI only; it never claims or causes goal completion. ECI never calls `UpdateGoal(status: "complete")` during or after this route. Preserve every visible goal, including one ECI created. Cancel, withdraw, replace, explicit workflow switch, and closure withdrawal remain exclusively under **Goal-backed user closure**.

After a clean review:

1. Keep the ECI marker armed and call `GetGoal`.
2. For an active goal, complete or recover teardown steps 1–4 with a non-terminal `clean-pass-pending:` report. Tell the user exactly: `Run /goal pause. After the host confirms the pause, send: finish ECI clean pass.` Do no root work while pending; on any continuing goal turn, repeat only that instruction. For a paused, blocked, or absent goal, complete or recover steps 1–4 and continue.
3. On `finish ECI clean pass`, call `GetGoal` again. An active goal stays pending and repeats only the pause instruction. A paused, blocked, or absent goal continues. Changed visible fields are irrelevant; preserve whatever is visible.
4. For nested ECI under ATE, preserve the shared goal. While the ECI marker remains armed, verify the outer ATE guard is armed or arm it before closing ECI.
5. Immediately before teardown step 5, call `GetGoal` again. An active goal returns to the pending route; do not run step 5. For a paused, blocked, or absent goal, finalize `clean-pass:` with `goal-disposition: absent|preserved-paused|preserved-blocked` and `goal-completion: not-claimed`, then run step 5. If interrupted before step 5, repeat this final check on recovery.

After ECI closes, the user may explicitly `/goal resume`. For nested ATE, invite resumption only after the outer guard is active and ECI is closed. ECI makes no goal-completion claim.

### Goal-backed user closure

This subsection is the sole contract for cancel, withdraw, replace, and workflow-handoff intent while ECI owns the root. Natural-language intent never means goal `complete` or `blocked`, never executes or pretends to execute a slash command, and never authorizes marker removal by itself.

At closure intent:

1. Call `GetGoal`. Record its complete visible snapshot, the old root's unfinished scope, the disposition (`retire`, `replace`, or `workflow-handoff`), the successor when known, marker state, and teardown progress.
2. Keep the ECI marker armed through teardown steps 1–4. A pending report uses a non-terminal `user-closed-pending:` certificate; never pass it to `eci-active off`.
3. `GetGoal` exposes no stable goal ID. Compare only visible fields, never invent identity, and treat a conflicting or ambiguous visible goal as **unexpected different**.

#### Retire a matching visible goal

Complete or recover teardown steps 1–4 while armed. Then tell the user: `Run /goal cancel. After the host confirms cancellation, send: finish ECI closure.` Until that follow-up or an explicit withdrawal, do no root work; on any continuing goal turn, repeat only that instruction.

On `finish ECI closure`, call `GetGoal`:

- Retiring goal still visible: keep the marker and pending certificate, do no root work, and repeat only the cancellation instruction.
- No goal: recover steps 1–4, call `GetGoal` again immediately before step 5, replace `user-closed-pending:` with final `user-closed:`, then run `eci-active off`.
- Unexpected different goal: use the route below.

Without the follow-up, closure remains incomplete and the marker and pending record stay armed. If host cancellation occurred, the goal cannot continue; otherwise any continuing goal turn must repeat only the cancellation instruction.

#### No goal at closure intent

Complete or recover teardown steps 1–4, then call `GetGoal` again immediately before step 5. Only a second no-goal result permits promotion to final `user-closed:` and `eci-active off`; a newly visible goal uses **unexpected different**.

#### Unexpected different goal

Never call `UpdateGoal`, `CreateGoal(..., replace: true)`, or infer a goal ID. If the visible goal is active, tell the user to run `/goal pause` and, after the host confirms the pause, send `finish ECI closure`; until then, do no root work and repeat only that instruction. On follow-up, require `GetGoal` to show the goal paused. A goal already paused or blocked needs no pause request.

After the different goal is verified non-active, complete or recover old teardown steps 1–4, finalize the old `user-closed:` report, close the old marker, immediately arm the successor workflow guard before work or yield, then invite the user to resume the preserved goal.

#### Planned replacement

Record the successor before retiring the old goal. Use the matching-goal cancellation handshake, including teardown steps 1–4 before asking for cancellation. After the host confirms cancellation, verify absence, recover and finalize old teardown, close the old marker, arm the successor workflow guard, and only then create or start the successor under the explicit goal predicate. Never use `replace: true` to collapse these transitions.

#### Workflow-only or nested-ATE handoff

Preserve the goal. Record the handoff, ask the user to run `/goal pause` and later send `finish ECI closure` after the host confirms the pause, then verify `paused`. Complete or recover teardown steps 1–4, close the old marker, arm the successor workflow guard, and only then resume the goal under the user's explicit handoff instruction.

#### Withdrawal and recovery

- Withdrawal before the old goal disappears: call `GetGoal`. If the recorded visible goal remains, replace the stale `user-closed-pending:` certificate with a non-terminal closure-withdrawn checkpoint, restore the armed gated workflow, and resume only work authorized by the latest request; absence or an unexpected different goal uses its route above.
- Withdrawal after disappearance: never treat the retired goal as resumed. Finish closure; continued autonomous work requires a fresh goal authorized under the explicit goal predicate.

| Observed recovery state | Required action |
|-------------------------|-----------------|
| Recorded goal present; marker on | Resume the applicable cancel/pause handshake; do no root work |
| Recorded goal absent; marker on | Recover steps 1–4, recheck absence immediately, then finalize and run step 5 |
| Recorded goal absent; marker off | Closure is complete; clear any stale pending state |
| Any goal present; marker off | Re-arm the workflow guard before any work, then classify the visible state |

This protocol requires cooperative host actions and a later user follow-up. Automatic atomic closure requires provider support for a model-visible pause/cancel operation or a goal-aware atomic marker transition.

## Prerequisites

For coding tasks, every affected agent prompt names the governed scope and every matching installed coding-style skill. A matching skill is required when present and must be loaded before handling that scope; loading it is not evidence of compliance.

### Coding-style admission

Coding-style guidance is a presumptive baseline only when choosing among otherwise correct alternatives. It does not soften any non-style requirement. A requirement remains non-style when violating it would make behavior, a name or interface claim, security, root-cause analysis, a test/proof/TDD obligation, or an approved architecture, file-ownership, purpose, or interface contract false. Follow every applicable non-style skill requirement.

For each governed scope, admit style once before its first durable write; group artifacts only when their governance matches. Reuse that admission until the scope, source, conflict, or deviation changes. Before admission, resolve the exact applicable governing instruction clauses, project/repository anchors, formatter/linter configuration, referenced standards, and matching installed coding-style skills. Use exact clause, `path#heading`, config-key/rule, or skill anchors, plus pertinent exclusions where scope could be confused. Load every matching installed style skill; a no-match result does not erase other sources, and invocation alone is not compliance.

An independent reviewer re-resolves applicability and admits only the route or routes needed for each governed scope or covered portion:

| Route | Required record |
|-------|-----------------|
| **Style Brief** | Governed scope; exact sources; grouped material guidance followed as `guidance -> choice`; every intentional deviation with baseline and purpose, exact scope, contemporaneous technical evidence, proportionality, and alternative/trade-off; independent reviewer and workflow verdict. |
| **Tool route** | Pre-write: governed scope, exact tool/config anchor, covered mechanical domain, and independent confirmation that no uncovered judgment, conflict, or deviation remains. Post-write: actual scope, command, and clean result. This discharges only the covered domain, including inside substantive work. |
| **No-source verdict** | Governed scope; governing instruction ancestry; repository/config/reference discovery basis; installed style-skill catalog checked; independent reviewer and workflow verdict. |

Create no empty record and no rule-by-rule inventory. A deviation may rely on governing sources, repository/task constraints, authoritative framework/toolchain documentation or source, or a faithful experiment. Convenience, deadline, authority, fatigue, sunk cost, precedent, and completed work establish no technical merit, alone or bundled. A higher-priority instruction mandating the concrete choice governs; otherwise resolve conflicting style baselines on technical merits.

Explicitly disposable exploration, PoCs, and repros may proceed in isolated scope before admission, but may not be merged, copied, adapted, or cited as style precedent. After final-scope admission, reuse is limited to what it permits; a faithful experiment may supply technical evidence but never establishes precedent by itself.

New scope, source, conflict, or deviation pauses only its affected work before the next write. Independently approve a local or tool-covered delta through `critic-step2`; route substantive drift through Steps 1 and 2. Final review independently reconciles actual changed scope, initial admission, approved deltas and deviations, and post-write tool evidence.

Cosmetic style remains NIT. Missing or unverified admission, omitted material guidance, or an undeclared or unjustified deviation is a blocking requirement/design failure; an admitted deviation is compliant. This contract makes declared discovery and omissions auditable; it neither proves nor claims exhaustive discovery.

## Blocker handling

Use `blocker-resolution-protocol` only after normal ECI issue handling cannot resolve a stall, after Step 2 post-bounce all-REJECT outcomes, or after gate/cycle limit hits before hard escalation.

Concrete bug/failure/flake/perf/incorrect behavior -> debugging iteration (`debugging-discipline`), not BRP; BRP only if debugging itself is blocked with an attempt log, hits its cap, or needs user-owned input.

ECI adapter:
- Keep ECI active while resolving blockers.
- Subagent-blocked != mission-blocked. Try normal ECI issue handling first; BRP is last resort before hard escalation.
- Use the separate `brainstormer` role for genuine stalls and Step 2 all-REJECT caps.
- Run a BRP primary explorer and separate `brp-feasibility-validator` before routing brainstormer output onward.
- Feed the blocker record, validated feasible ideas, primary explorer facts, and prior failures into the next explorer or implementer message.
- Use the separate `loop-breaker` role at gate/cycle limits before hard escalation.
- Hard escalation reports the blocker requiring user input; it does not disengage ECI.

## Engagement marker

The PreToolUse gate `~/.kimi-code/hooks/eci-active-gate.sh` denies direct Edit/Write on the main thread while engaged. Every code change must flow through a spawned agent. Spawned agents write from their own session; the marker is keyed to the orchestrator's session and must not block them.

| Step | Command | When |
|------|---------|------|
| Engage | `KIMI_SESSION_ID=<session_… id from the hook_result context line> ~/.kimi-code/bin/eci-active on "<task + scope>"` (if no id is in context, run the command bare; on refusal, re-run with the id it prints) | Before Step 1 of the first iteration |
| Disengage | See Teardown sequence below | Clean pass or **Goal-backed user closure** authorizes step 5 |
| Hard escalate | Report blocker requiring user input; marker stays active | ECI cannot proceed without user input |

Do not disengage mid-task to escape the gate — that is the regression this marker exists to catch. If a hand-edit feels necessary, send the work to the persistent `implementer` agent.

## Team setup

**Persistent agent** = spawned once with foreground `Agent`, then reused with foreground `Agent` and `resume`. **One-shot agent** = a fresh foreground `Agent` call for one bounded assignment. Background agents are reserved for independent work.

Persistent agents handle Step 1 (explorer) and Step 3 (implementer) across iterations. Every critic-role invocation (Step 2 critic, Critic A, Critic B, brainstormer, brp-feasibility-validator, loop-breaker) and each E2E gate uses a fresh agent, distinct from the explorer and implementer. The producer must never act as critic.

**"Persistent" != "carries cross-iteration context".** The persistent agent's spawn-prompt baseline already forces fresh-assignment treatment each message (re-read referenced files, no prior-turn trust). Spawning a new agent for Step 1 or Step 3 because "fresh context is needed" defeats the persistent role — resuming the existing agent already gives that. The producer-vs-critic split is about *agent identity for adversarial separation* (critic must not be the producer), not about context staleness.

**Reusable role rule.** Spawn stable role slots, not task/round-specific identities. Use the tool's reusable `subagent_type` values (`explore`, `coder`, `plan`); carry ECI identity in the spawn prompt, roster label, and resume messages. Put changing details (`round`, `gate`, `scope`, `lens`) in the assignment, not the role name.

**Critic identity rule.** Step 2 critic, Critic A, Critic B, brainstormer, brp-feasibility-validator, and loop-breaker use separate stable role labels (`critic-step2`, `critic-A`, `critic-B`, `brainstormer`, `brp-feasibility-validator`, `loop-breaker`). Adversarial separation = identity rule (critic != producer). Start every critic round or invocation with a fresh `Agent` spawn under its stable label; never resume an earlier critic to obtain fresh context. Critic B's Packet 2 alone resumes the Packet 1 agent because both packets form one invocation.

Kimi does not use `CLAUDE_ROLE`, `TeamCreate`, `team_name`, or independent tmux/CLI agents for ECI. Role identity is carried in the spawn prompt, roster label, and subsequent resume messages.

### Spawning

| Action | Command |
|--------|---------|
| Spawn explorer | `Agent` with `subagent_type: "explore"` and role label `explorer` |
| Spawn implementer | `Agent` with `subagent_type: "coder"`, role label `implementer`, and explicit file/module ownership |
| Spawn Step 2 critic | `Agent` with `subagent_type: "explore"` or `coder`; role label `critic-step2`; assignment includes round number |
| Spawn Step 4 critic-A / critic-B | Parallel `Agent` calls with role labels `critic-A` / `critic-B` |
| Spawn E2E agent | `Agent` with `subagent_type: "coder"`; role label `e2e-gate`; assignment includes gate number |
| Spawn brainstormer | `Agent` with `subagent_type: "explore"` and role label `brainstormer` |
| Spawn BRP feasibility validator | `Agent` with `subagent_type: "explore"` or `coder`; role label `brp-feasibility-validator` |
| Spawn loop-breaker | `Agent` with `subagent_type: "explore"` and role label `loop-breaker` |

Every spawned agent prompt states the role name, original user requirements, exact scope, expected output, and that other agents may be editing in parallel. Exception: Critic B Packet 1 for code diffs contains only role label, stop-hook/reporting boilerplate, code diff, and reconstruction instruction; omit original requirements, exact scope, ledger/task/design context, rationale, commit message, and prior review output until Packet 2.
Every spawned ECI agent prompt must also state: "Follow any Stop-hook prompt in that session, including required proof/checklist files. Fix blockers within assigned scope. Report to the orchestrator only when resolution needs out-of-scope changes, unrelated user work, credentials, or approval."

### Explorer spawn-prompt baseline

Per-message body in Step 1.
- Role label per Spawning table.
- "Treat each new task message as a fresh assignment per Step 1 of the ECI skill. Re-read every referenced file each turn — do not trust prior-turn reads."

### Implementer spawn-prompt baseline

Per-message body in Step 3.
- Role label per Spawning table.
- "Treat each new task message as a fresh assignment per Step 3 of the ECI skill. Re-read every file you intend to modify each turn."
- One commit per logical change.
- Code/debugging submissions include root-cause rationale plus regression status/explanation when applicable: cause chain, evidence, and why the diff repairs the cause. Unknown "why" = unsubmittable.
- Every factual claim in submission carries a T1-T5 tag per AGENTS.md Claim Verification protocol. E2E evidence ("tests pass", "build succeeded", screenshots, observed state) cited as T1 with tool output, log path, or screenshot file. Concrete example: "[T1: `go test ./...` exit 0, all 47 pass]" not bare "tests pass". Untagged "all green" = unsubmittable.

## Teardown sequence

Run in this exact order on disengage. Stopping mid-sequence keeps the gate armed.

1. Write disengage-report markdown (content per **Disengage report** below); goal-preserving clean pass and goal-backed closure use their pending-to-final certificate transitions defined above.
2. Resume `implementer` in the foreground (`Agent` with `resume`): `commit any uncommitted work and confirm clean tree`; use its returned result as the acknowledgement.
3. Confirm every dependency-producing `Agent` call completed in the foreground. Let independent background work report through automatic completion notifications.
4. For any known background task still running, let its notification finish it unless the task itself genuinely must be cancelled. Only then call `TaskStop` with its exact task ID and a reason. Do not stop terminal tasks or use `TaskStop` as an agent close/reset operation.
5. `~/.kimi-code/bin/eci-active off <report.md>` (LAST — keeps the gate armed if teardown fails partway; goal-preserving clean pass and goal-backed closure must first satisfy their final rechecks and guard ordering).

If the orchestrator's next Stop blocks, follow the hook prompt and use the disengage report as the verification summary.

### Disengage report

`~/.kimi-code/bin/eci-active off` requires a markdown report walking the stop checklist (`~/.kimi-code/hooks/stop-checklist.md`) and critically analyzing items that could not be fully complied with during the ECI scope. Required sections:

```
## ECI completion certificate
<exactly one of: clean-pass: <evidence> | user-closed: <evidence>>

## Stop checklist walkthrough
- Questions: pass/fail/N-A — <one-line evidence>
- Git: pass/fail/N-A — <one-line evidence>
- Completion: pass/fail/N-A — <one-line evidence>
- Root cause: ...
- Adversarial self-critique: ...
- Assumed blockers: ...
- Rule-compliance self-audit: ...
- Project understanding ledger: ...
- Testing: ...

## Incomplete compliance
- <item> — could not fully comply because <reason>; impact: <what slipped>
- ...
fully-compliant: <reason rule-by-rule>   # only if no incomplete items
```

The bin rejects reports missing `## Stop checklist walkthrough`, `## Incomplete compliance`, non-empty bodies, and exactly one terminal verdict marker: `clean-pass:` or `user-closed:`. Include either all full stop-verification sections or `## ECI completion certificate`. Validation is a content gate, not a wordcount — write substance, not boilerplate.

The template is the final form. A goal-backed pending report uses `user-closed-pending:` under **Goal-backed user closure**, so it intentionally cannot authorize `eci-active off` until revalidated and promoted.

Under **Goal-preserving clean pass**, use `clean-pass-pending:` until the final `GetGoal` recheck; it cannot authorize `eci-active off`. The final `clean-pass:` evidence includes `goal-disposition: absent|preserved-paused|preserved-blocked` and `goal-completion: not-claimed`.

Full stop-verification sections: `Summary`, `Verification`, `Requirements`, `Root Cause`, `Claim Inventory`, `Pre-Mortem`, `Adversarial Critique`, `Rule-Compliance Self-Audit`, `Gaps`.

## Loop structure

Each iteration tackles one change. All four steps run per iteration. Do not advance to next change until current one passes all steps.

| Step | Phase | Actor | Output |
|------|-------|-------|--------|
| 1 | Explore | Persistent `explorer` agent (`Agent` with `resume`) | Ranked options + cited sources |
| 2 | Critique explorations | Fresh `critic-step2` agent per round under the same role label | Winner with concrete text + tagged CONDITIONAL/NIT list (one explorer revision round permitted on all-REJECT) |
| 3 | Implement | Persistent `implementer` agent (`Agent` with `resume`) | One diff |
| 4 | Review gate (parallel) | Critic A + Critic B, plus E2E when in scope | Run all in-scope agents concurrently; collect every in-scope result |
| Exit | Finalize | Main thread | Apply / commit / report |

Agent separation: see Red Flags. Main thread orchestrates; agents produce.

**Completion-locked waiting.** Use foreground `Agent` when the next step depends on the result. Run only independent work in the background and accept its automatic terminal notification. `TaskOutput(block=false)` may take a deliberate status snapshot; never use blocking `TaskOutput` for ECI agent work. Never sleep, poll, or tight-loop repeated waits.

### Bug-discovery routing

If any ECI agent, gate, or user followup discovers a concrete bug (failure, flake, perf regression, or incorrect behavior), route the bug through a debugging iteration or nested ECI pipeline. Main thread only coordinates.

An explicitly isolated disposable repro may run before coding-style admission under the contract above. It may supply technical evidence, but a production fix or reuse of repro code waits for admission of the final governed scope.

Map `debugging-discipline` to separate delegated ECI roles: repro -> `repro` worker; RCA/regression -> `rcaer` explorer; critic -> Step 2 critic; fix -> implementer; review -> Critic A/B + E2E gate. Every bug prompt says: "Load `debugging-discipline`; follow its repro/RCA-critic/fix-review loop. Determine `regression: yes/no/unknown`; if regression, explain how it happened. Do not submit until root cause is falsifiable and the fix is proven on the real failing path."

Before sending the RCA/regression assignment, write or update a human-readable regression report file: `~/.cache/kimi-proof/$SESSION_ID/eci-regression-reports/<task>.md` when `$SESSION_ID` exists; otherwise `./.kimi-code-regression-reports/<task>.md`. Include bug statement, repro, previous/current test-run artifact paths, CI/log/release/QA evidence, known-good/current-bad anchors, regression status, missing evidence, and the regression explanation once known. Send the report path and evidence packet to `rcaer`. Human reading is optional; never block the pipeline waiting for user review.

## Step 1: Explore

Resume the persistent `explorer` agent (`Agent` with `resume`). Each per-message body must include:
- The problem/change for THIS iteration, in full context.
- What's already been tried or ruled out (iterations 2+: include results from prior iterations, current codebase state, and last blocking gate issues verbatim if a prior cycle's gate failed).
- Exact file paths of existing related code — explorer must re-read them this turn to avoid suggesting duplicates. "Re-read referenced files; do not trust prior turn reads."
- For every governed coding scope, resolve applicable style sources and propose only the needed Style Brief, Tool route, and/or No-source verdict under **Coding-style admission**. Step 1 owns the proposal; Step 2 owns admission.
- Required output: ranked options, each with {what, why, where it applies, cost, tradeoffs}.
- Every factual claim in the report must carry a T1-T5 tag per AGENTS.md Claim Verification protocol. Primary sources only for T1. Untagged factual claims are not allowed.
- Word cap on the report (default: 1000 words).

### Proof of Concept Requirement

Any proposed option whose core mechanism is unproven-in-practice (not a well-known pattern, not already shipped in this codebase, not a documented vendor API used as documented) ships with a minimal PoC alongside the proposal:

- Strip every concern not needed to exercise the core mechanism — no error handling, no edge cases, no production polish, no scaffolding beyond what the demo requires.
- Run end-to-end on one real input; produce the observable behavior the mechanism claims.
- Explorer attaches the PoC to the option in Step 1. Missing PoC on an unproven option = Step 2 REJECT.

Proven-in-practice mechanisms need no PoC. State "proven by <link/citation>" when claiming exemption.

An isolated disposable PoC may precede coding-style admission, but production reuse waits for the final-scope admission and is limited to what that admission permits. The experiment may be evidence; it is never style precedent.

## Step 2: Critique explorations

Spawn a DIFFERENT foreground agent — not the explorer, not the main thread. The critic identity must differ from explorer and implementer. Use the stable role label `critic-step2` (Step 2) or `critic-A` / `critic-B` (Step 4); put the round number in the assignment. Each round starts with a fresh `Agent` spawn under that label. MUST NOT reuse the persistent explorer, implementer, or a critic from an earlier round.

The critic's prompt must include:
- **Original user requirements verbatim.** The critic must verify options against what the user actually asked for, not just technical soundness.
- **"Step 0 — Independent baseline."** Read the source material (target file, existing code, prior art) and write your own 3-5 bullet assessment BEFORE opening the explorer's report. Include this baseline in the critique output.
- "Assume every suggestion is wrong until you prove otherwise."
- "Read the current state first" (the file/code/doc the explorer was working on) — verify duplication claims independently.
- **Coding-style admission.** Before Step 3, independently re-resolve applicability and either admit the explorer's exact record or issue a REJECT. Do not accept skill invocation, the explorer's conclusion, or a bare no-match/no-source claim as proof. The admitted record is handed to the implementer verbatim.
- **Claim-scope audit for governance/prompt/hook/protocol/reviewer changes:** record mechanism/predicate, emitted or user-facing wording, strongest wording evidence supports, and one boundary counterexample. REJECT certainty, classification, provenance, or authority wording beyond mechanism evidence. Silent `UserPromptSubmit` state maintenance does not prove the user's work is non-trivial. `prompt-task-reminder.sh` maintains prompt state silently; optional LLM first-tool admission review is separate `PreToolUse` behavior configured through `KIMI_EDIT_PRE_REVIEWER`, with `LLM_EDIT_PRE_REVIEWER` and `CLAUDE_EDIT_PRE_REVIEWER` accepted only as lower-precedence compatibility aliases when earlier variables are unset.
- **Cite-verify and tag-discipline protocol:**
  - Untagged factual claim from explorer = REJECT-tagged issue on the option that depends on it.
  - Fetch every T1/T2 URL via FetchURL; use Read for source-code citations.
  - Unfetchable URL (auth-gated, internal, tool unavailable) → flag "unverified — could not fetch" + state whether dependent claim is load-bearing.
  - Load-bearing = any citation justifying picking an option as winner, or justifying a REJECT verdict that bounces an option to the explorer. Load-bearing + unfetchable = issue.
  - Quote the exact supporting passage. Flag hallucinated URLs, misquotes, and training-recall mislabeled as T1.
  - Non-load-bearing citations may be skipped if explicitly marked "non-load-bearing: no verdict depends on this source."
  - T3/T4: sample, not exhaustive.
- Per-issue severity code (table below). Issues attach to specific options. Aggregate per-option verdict = strongest severity.
- **DUPLICATE-of-#N marker** (orthogonal to severity): set when one option restates another option's substance.
- **If at least one option has zero REJECTs**: pick winner from that set with CONCRETE TEXT. Output winner + that option's CONDITIONAL fix-text list (verbatim) + NITs (informational).
- **If every option has REJECTs**: do not pick. Return REJECT issues verbatim to orchestrator for bounce per Loop-logic table.
- Single-option explorations get the same adversarial treatment.
- "Be harsh. Most suggestions are noise. Zero survivors is a valid outcome."
- Each retry round uses a fresh critic spawn under the same stable role label.

### Step 2 severity codes

| Code | Meaning | Effect on the option |
|------|---------|----------------------|
| **REJECT** | Option is wrong-shaped: violates user requirements, rests on unsound assumption, lacks a critical capability, or is unfixable without re-exploration | Option cannot be the winner. If ALL options have ≥1 REJECT, see Loop-logic. |
| **CONDITIONAL** | Option is sound; needs a specific tweak the critic spells out as one-or-two lines of fix-text | Option remains viable. Orchestrator folds the fix-text into Step 3 (see below). |
| **NIT** | Soft preference; doesn't affect viability | May be ignored when picking the winner |

Same vocabulary as Step 4; Effect column differs because receiver/artifact/remediation differ per phase.

For coding-style issues, cosmetic preference is NIT; missing or unverified admission, omitted material guidance, or an undeclared or unjustified deviation is REJECT. An admitted deviation is compliant. Classify hard non-style failures by their existing requirement, not as style.

### Step 2 loop-logic

| Critic verdict pattern | Action | Output |
|---|---|---|
| ≥1 option with zero REJECTs | Pick highest-ranked clean option as winner | Winner + that option's CONDITIONAL fix-text list + NITs |
| Every option has ≥1 REJECT, round 1 | Bounce verbatim REJECT reasons to explorer; explorer revises; spawn a fresh `critic-step2` for round 2 | Bounce-back |
| Every option has ≥1 REJECT, round 2 | Trigger brainstormer per Brainstormer trigger row; new explorer round | Escalation per Escalation table |
| Only NITs across all options | Pick highest-ranked option directly | Winner + NITs |

**Critic emits issues only.** CONDITIONAL absorption happens at the orchestrator's hand-off to Step 3 — orchestrator folds the winner's CONDITIONAL fix-text into the Step 3 implementer resume-message body. The critic does NOT rewrite options.

## Step 3: Implement

Resume the persistent `implementer` agent (`Agent` with `resume`). One change, one diff per message. Code tasks: implementer invokes `test-driven-development` and `debugging-discipline`, loads every matching installed coding-style skill, applies the admitted coding-style record, and re-reads every file it intends to modify on each new task message.

Each new task message to `implementer` includes:
- The current iteration's concrete-text from the Step 2 critic (verbatim).
- The current governed scope's admitted coding-style record and reviewer verdict (verbatim), including any approved deltas and applicable Tool route.
- Iterations 2+: prior iteration's gate findings (verbatim) and files changed since the last message.
- Step 2 CONDITIONAL fix-list (verbatim, if any) — implementer applies these alongside the concrete text.
- Code/debugging submissions include root-cause rationale plus regression status/explanation when applicable. A fix must identify and repair the mechanism that causes the failure. No causal link may remain unexplained. Any change that only alters the failure's frequency, timing, visibility, or blast radius is mitigation unless containment was explicitly requested.
- Submission tags every factual claim. Untagged claim → orchestrator bounces back without spawning the gate (parallel to E2E-evidence rule).

Before the next affected write, the implementer reports any new style scope, source, conflict, or deviation. Continue unaffected work. Send a local or tool-covered delta to a fresh foreground `critic-step2` for independent approval. Substantive drift resumes the explorer through foreground `Agent` with `resume` and reruns Steps 1 and 2. Do not create a new record for each edit when the admitted governed scope is unchanged.

**Affected-path E2E before submit.** Runtime behavior reachable via UI/API/device/CLI: build, run full tests, exercise affected user path, cite output/screenshot/state. Proxy evidence alone insufficient. Skip docs, prompts, config-only, tests-only, pure refactors. If E2E unavailable, report BLOCKED with the exact missing resource; missing E2E/rationale → bounce before Step 4.

If applicable E2E evidence is missing, resume the implementer with: "Missing E2E evidence — build, run full suite, exercise user path, cite output/screenshot/state. Do not resubmit without evidence."

## Step 4: Review gate (parallel)

Spawn all in-scope reviewers as fresh foreground agents in a single message: `critic-A` and `critic-B` always, plus `e2e-gate` only when **Affected-path E2E** applies. Each MUST NOT message the persistent `explorer` or `implementer` agent. Their foreground calls return the results; evaluate only after collecting every in-scope result. Every reviewer prompt must include the **original user requirements verbatim** — reviewers catch requirement deviations, not just technical issues.

Critic B code-diff exception:
- Code diffs use two packets. Skip Packet 1 when there is no code diff.
- Packet 1 is diff-only isolation. Spawn a fresh `critic-B` for it.
- Packet 1 contains only role label, stop-hook/reporting boilerplate, code diff, and reconstruction instruction. It is exempt from original requirements, exact scope, and normal review context.
- After `reconstructed intention:` returns, resume that same Packet 1 agent with Packet 2 containing the original requirements and full Critic B context.
- Gate incomplete until Packet 2 returns.

### Issue severity codes

Every issue from Critic A and Critic B must carry exactly one code:

| Code | Meaning | Effect |
|------|---------|--------|
| **REJECT** | Would make the change wrong, unsafe, or contradictory | Must be fixed; routing follows impact/evaluation rules below |
| **CONDITIONAL** | Fix needed, but specific enough for the implementer to apply without redesign unless impact requires it | Must be fixed; routing follows impact/evaluation rules below |
| **NIT** | Soft recommendation | May be ignored |

Both critics tag every issue per the severity codes table above. Same vocabulary as Step 2; Effect differs (re-implement vs. re-explore).

For every REJECT or CONDITIONAL, reviewers must also tag `impact: trivial` or `impact: substantive` with a one-line rationale. `substantive` means non-trivial, major, API-changing, contract-changing, architecture-changing, security-sensitive, persistence-affecting, concurrency-affecting, or requiring a design tradeoff. Use the Triviality rule above for impact tags. Small patches are substantive when they alter future behavior, decision rules, contracts, prompts/instructions, or review routing. Missing impact tag = REJECT against the review output; re-prompt that reviewer before evaluating the gate.

Both critics critique the implementer's root-cause rationale and regression explanation when applicable. Unknown causal link or symptom-only change = REJECT unless containment was explicitly requested.

For governance/prompt/hook/protocol/reviewer changes, Critic A and Critic B perform the Step 2 claim-scope audit. REJECT overclaims and missing boundary/negative tests; silent `UserPromptSubmit` state maintenance must not be described as reminder emission or an LLM reviewer/classifier. Optional LLM first-tool admission review is separate `PreToolUse` behavior configured through `KIMI_EDIT_PRE_REVIEWER`, with `LLM_EDIT_PRE_REVIEWER` and `CLAUDE_EDIT_PRE_REVIEWER` accepted only as lower-precedence compatibility aliases when earlier variables are unset.

### Critic A — correctness

Emit only issues affecting correctness, safety, or fidelity to the concrete text. Interface contract fulfillment — does every interface implementation actually work, not just compile? Polish and taste items are NITs at most.

Under **Coding-style admission**, Critic A guards the non-style boundary by consequence. False behavior, name/interface claims, security, root-cause analysis, test/proof/TDD obligations, or approved architecture, file-ownership, purpose, and interface contracts remain hard failures; they cannot be excused as style deviations. Guidance selecting among otherwise correct alternatives remains style.

Tag-discipline audit: every factual claim in the implementer's submission must carry a T1-T5 tag per AGENTS.md Claim Verification protocol. Untagged factual claim = REJECT.

### Critic B — long-term health

Different agent from Critic A.

Diff-only intention check:
- Code diffs only. Skip when there is no code diff.
- Before Packet 1, spawn a fresh `critic-B`.
- Packet 1 contains only role label, stop-hook/reporting boilerplate, code diff, and reconstruction instruction.
- Exclude original requirements, exact scope, ledger/task/design context, rationale, commit message, implementer or teammate summaries, and prior review output.
- Output `reconstructed intention:` with 2-4 bullets covering apparent root reason and intended behavior change, then stop.
- Main thread compares the reconstruction with the actual root reason and desired effects.
- If it misses the root reason, relies on hidden context, or claims an undesired effect, add a `CONDITIONAL` follow-up with the normal `impact:` tag to make code, tests, names, comments, or commit message explain the change.
- Packet 2: resume the Packet 1 agent and continue the same long-term-health review with full context.

Focus — adversarial, long-term lens:
- **Tech debt**: Coupling, hidden dependencies, or shortcuts costing more to fix later than now?
- **Coding-style admission**: Independently re-resolve actual governed scope and matching installed skills, then reconcile the diff with the admitted record, approved deltas/deviations, and post-write Tool evidence. Loading a skill alone proves nothing. Missing or unverified admission is blocking; an admitted deviation is compliant, and cosmetic taste is NIT.
- **Code smells**: God methods, feature envy, primitive obsession, duplicated logic, unclear names, missing/premature abstractions. Flag only smells that materially hurt readability or maintainability.
- **Architectural fit**: Right layer? Respects module boundaries? Code in correct binary/package per its stated purpose?
- **Tag-discipline**: every factual claim in submission carries T1-T5 per AGENTS.md Claim Verification. Untagged factual claim = REJECT.

Emit only issues that matter for long-term health. "Would refactor eventually" is not an issue — "will cause bugs or confusion within 3 months" is.

### E2E agent — end-to-end verification

E2E is in scope only for code/debugging tasks with affected runtime behavior under **Affected-path E2E**. Skip it for docs, prompts, config, skills, design, tests-only changes, and pure refactors.
E2E capacity bottlenecked (device/browser/env slots, credentials, long setup): batch only then. While waiting, debug via shortest faithful repro (unit/API/CLI/log replay/component) before full E2E. Wait briefly for imminent tasks only if no slot idles; keep healthy batches running; queue late arrivals; report per-task verdicts.

1. Build; failure = issue.
2. Run full suite; failure = issue.
3. Exercise affected user path through real UI/API; cite output/screenshot/state. Proxy evidence alone insufficient.
4. Check related regressions.

### Evaluating results

Collect every in-scope result: Critic A and Critic B, plus E2E when in scope. Apply severity logic:

Critic B's coding-style reconciliation is part of the gate. Route a substantive admission invalidation or substantive drift through Steps 1 and 2. Send a local or tool-covered delta to a fresh foreground `critic-step2` before the next affected write. Final acceptance requires reconciliation of actual changed scope, admission, approved deltas/deviations, and Tool evidence.

- At least one substantive REJECT or substantive CONDITIONAL, OR an E2E failure caused by design/API uncertainty → batch all REJECTs, CONDITIONALs, and E2E failures into one design-revision issue list → return to Step 1/Step 2 explorer/designer-critic loop → Step 3 implements the selected revised design plus the full batch → re-run gate.
- At least one trivial REJECT from Critic A or Critic B, OR any trivial E2E failure → fix all REJECTs, CONDITIONALs, and E2E failures in one implementer message → re-run gate.
- Zero REJECTs but only trivial CONDITIONALs exist → fix all CONDITIONALs in one implementer message → re-run the gate.
- Only NITs → gate passes.

Gate retry and cycle limits defined in Escalation table.

**Clean pass** = zero REJECTs + zero CONDITIONALs, plus E2E pass when E2E is in scope, all from the same post-fix gate run.

### Design-revision issue batch

When the gate routes back to design revision, batch issues before contacting any agent. Do not run one loop per issue.

The batch must include:
- All REJECTs, CONDITIONALs, and E2E failures from the completed gate, grouped by affected artifact/API/contract.
- Source agent, severity, impact tag, file:line or direct evidence, and the exact quoted issue text.
- Acceptance criteria for resolving the whole batch.

Step 1 explorer re-reads current code and researches options that resolve the full batch. Step 2 critic reviews those options as the designer-critic and either selects one concrete revised design or bounces all-REJECT outcomes per Step 2 loop-logic. Step 3 implementer receives the selected revised design and the full issue batch verbatim. No direct patching of substantive findings before this loop.

## Brainstormer (unblocker)

Fresh idea generator — fires on-demand when the cycle stalls. Output is raw ideas only; never decisions, verdicts, or filtering. Bigger list = better.

**Genuine stall definition.** Normal ECI issue handling was tried, and the Required Record from `blocker-resolution-protocol` exists. A bare "I'm stuck" without an attempt log is not a stall; push the agent to keep trying.

| Trigger | Action |
|---------|--------|
| Explorer returned zero viable options after documented attempts | Spawn brainstormer + BRP primary explorer -> run `brp-feasibility-validator` -> feed blocker record, validated feasible ideas, primary explorer facts, and prior failures into the next explorer/implementer prompt |
| Step 2 bounce cap reached (one explorer revision round did not yield a clean option) | Spawn brainstormer + BRP primary explorer -> run `brp-feasibility-validator` -> feed blocker record, validated feasible ideas, primary explorer facts, and prior failures into the next explorer/implementer prompt |
| Implementer genuinely blocked inside Step 3 (per Genuine stall definition above) | Spawn brainstormer + BRP primary explorer -> run `brp-feasibility-validator` -> feed blocker record, validated feasible ideas, primary explorer facts, and prior failures into the next explorer/implementer prompt |

### Prompt requirements

- Original problem + everything tried so far, verbatim.
- Current code/file paths — brainstormer reads them independently.
- "Generate as many distinct ideas as possible. No filtering, no feasibility judgment, no negatives. Bigger list = better."
- "You are NOT one of the cycle agents. Do not trust prior agent summaries."

### Constraints

- Spawn as separate `brainstormer` agent; never message the explorer or implementer agent.
- Must NOT be any other cycle agent (explorer, Step 2 critic, implementer, Critic A, Critic B, E2E, brp-feasibility-validator, loop-breaker).
- Each invocation uses a fresh `brainstormer` spawn — start each idea-burst clean.
- Ideas only — `brp-feasibility-validator` filters BRP-triggered ideas.
- Brainstormer output never goes directly to explorer/implementer after a BRP trigger; only validator-approved ideas may be routed onward.

## Loop-breaker

A separate agent — not any of the cycle agents — gets one chance to break the loop before escalating to the user.

**One loop-breaker invocation per change**, regardless of trigger. If the granted retry fails -> create a protocol-limit blocker record, run `blocker-resolution-protocol`, and hard escalate only if BRP finds no feasible internal path or the blocker is user-owned. ECI stays active.

### Prompt must include

- Original problem statement.
- All cycle attempts: what was tried, what failed, remaining issues verbatim.
- Current code state (file paths — loop-breaker reads them independently).
- "You are a fresh reviewer. Read the code and issues yourself. Do not trust prior agents' assessments."

### Decision — exactly one of

| Decision | Meaning | Effect |
|----------|---------|--------|
| **ACCEPT** | Remaining issues are cosmetic, speculative, or not worth another iteration | Accept current state with reasoning. Gate passes. |
| **RETRY** | Remaining issues are real and fixable | Grant exactly one more attempt (gate retry or full cycle, matching the trigger). Provide specific guidance. |

### Constraints

- Spawn a fresh separate `loop-breaker` agent for its invocation.
- Must NOT be any of the 6 cycle agents (explorer, Step 2 critic, implementer, Critic A, Critic B, E2E agent).
- Reads code and issues independently — no reliance on prior agent summaries.
- One invocation per change. Granted retry fails -> create a protocol-limit blocker record, run `blocker-resolution-protocol`, and hard escalate only if BRP finds no feasible internal path or the blocker is user-owned.

## Escalation

Single decision table for all limit hits. One loop-breaker per change total.

| Trigger | Condition | Action | If retry fails |
|---------|-----------|--------|----------------|
| Gate retry cap | 3 gate retries failed within one cycle | Invoke loop-breaker (if not yet used for this change) | Create protocol-limit blocker record -> run `blocker-resolution-protocol` -> hard escalate only if BRP finds no feasible internal path or the blocker is user-owned; ECI stays active |
| Cycle limit | 3 full cycles failed for one change | Invoke loop-breaker (if not yet used for this change) | Create protocol-limit blocker record -> run `blocker-resolution-protocol` -> hard escalate only if BRP finds no feasible internal path or the blocker is user-owned; ECI stays active |
| Loop-breaker already used | Either limit hit but loop-breaker was consumed by prior trigger | Create protocol-limit blocker record -> run `blocker-resolution-protocol` -> hard escalate only if BRP finds no feasible internal path or the blocker is user-owned; ECI stays active | — |
| Step 2 post-brainstormer all-REJECT | Brainstormer fired and new explorer's options still all-REJECT after one revision | Create protocol-limit blocker record -> run `blocker-resolution-protocol` -> hard escalate only if BRP finds no feasible internal path or the blocker is user-owned; ECI stays active | — |

**Hard escalate** = report a blocker requiring user input while ECI remains active. Use the escalation report from `blocker-resolution-protocol`, plus: (a) original problem, (b) what each cycle tried, (c) loop-breaker's assessment (if invoked), (d) last blocking issue, (e) next-best alternative from explorer's ranking. Silent punts forbidden.

### Goal anti-loop

Goal continuation never resets or extends any workflow retry, gate, cycle, loop-breaker, or BRP limit. A goal continuation may try a materially different feasible path; it may not repeat a capped step or unchanged failed action.

For each genuine non-terminal impasse, record in the project ledger: blocker fingerprint, consecutive blocked goal turns, evidence from the last attempted alternative, and what material change would reset the count.

Track blocked goal turns independently by exact task ID; activity on another task does not break that task's sequence. A blocked goal turn cannot advance because that task remains running. This rule counts goal-turn decisions, not `TaskOutput` calls, and authorizes no wait forbidden elsewhere. **Terminal output** explicitly reports that the task itself completed, failed, or was interrupted/cancelled. Timeout, silence, `running`, status-only data, an interrupted wait call, and partial output are non-terminal. Partial output may refresh activity evidence; it does not reset this counter.

| Prior state | Event for that task ID | New state and required action |
|---|---|---|
| No entry | Blocked goal turn without terminal output | Set `count=1`; record the task ID. |
| `count=1` | Later blocked goal turn without terminal output | Set `count=2`. |
| `count=2` | Later blocked goal turn without terminal output | Set `count=3` and latch `no-more-blocking`. Stop blocking on that task. Advance independent work, or classify/recover it only under existing stale rules. |
| Any count | Terminal output arrives | Clear the entry and route the terminal result. |

`count=3` does not itself prove staleness or authorize cancellation. A replacement task has a new ID and remains outside this same-ID guard, subject to existing workflow limits.

Hard escalation is the terminal case: three full cycles, loop-breaker, and BRP have all been exhausted. Call `UpdateGoal(status: "blocked")` at hard escalation — this IS the three-consecutive-turn threshold met.

## Iteration limit

Cycle limit defined in Escalation table (3 full cycles per change).

## Exit conditions

- All changes landed and **Goal-preserving clean pass** reaches its closed state, OR
- Loop-breaker ACCEPT → current state accepted with reasoning and **Goal-preserving clean pass** reaches its closed state, OR
- **Goal-backed user closure** reaches its closed state, including any required successor guard, OR
- Hard escalate triggered → blocker/user decision request reported; ECI remains active.

## Status reports

Reports to user use:

| Rule | Example |
|------|---------|
| Human-readable names, not task/iteration numbers | "severity-codes table done", not "task 3 done" / "cycle 2 failed" |
| Tree structure when work decomposes into sub-issues or nested ECI pipelines | Indent children under parent; never flatten |

- Use `<role label> (<runtime name> [type])` in every status, wait, or close update; do not use bare runtime nicknames once labeled.

Issue uncovered mid-iteration that spawns its own ECI pipeline → nest under the iteration that found it.

```
auth middleware swap
├─ severity-codes change: gate passed, committed
├─ E2E uncovered stale-session bug → nested ECI:
│   ├─ session-cache invalidation: 3 options ranked
│   └─ blocked on prod log access
└─ docstring update: pending
```

## Red flags

| Symptom | Fix |
|---------|-----|
| Implementing 2+ changes before re-critiquing | Stop. One at a time |
| "Good enough" at cycle 3 | Invoke loop-breaker, don't settle or force |
| Any two of {explorer, Step 2 critic, implementer, Critic A, Critic B, E2E agent, brainstormer, brp-feasibility-validator, loop-breaker} are the same agent | Banned. Up to nine distinct agents (six per normal cycle + brainstormer/validator for BRP + loop-breaker at limits) |
| Review-gate Critic A returned before Critic B was spawned | Sequential gate. Spawn Critic A + Critic B (+ E2E when in scope) in one message with parallel `Agent` tool calls; do not serialize even if one critic's view seems sufficient. |
| Task/round-specific role labels (`critic-r3`, `e2e-gate-7`) used instead of reusable role slots | STOP. Use stable labels (`critic-step2`, `e2e-gate`) and put round/gate details in the assignment. |
| Skipping E2E when **Affected-path E2E** applies | In-scope E2E is part of every review-gate run, not an end-only check; omit it when E2E is out of scope |
| Skipping exploration or critique for later iterations | Every iteration runs all four steps — none are optional |
| Winner lacks concrete text | Critic under-specified. Re-spawn with "concrete text required" |
| No rejected list in Step 2 | Critic is not adversarial. Re-spawn |
| Brainstormer output filters/judges/picks a winner | Brainstormer is idea-only. Re-spawn with "no filtering, no negatives" |
| Persistent explorer or implementer agent addressed for any critic-role work (Step 2 critic, Critic A, Critic B, brainstormer, brp-feasibility-validator, loop-breaker) | STOP. Spawn a separate critic agent; the producer (explorer/implementer) must never act as critic. |
| Clean-pass calls `UpdateGoal(status: "complete")`, claims goal completion, or resumes root work while pending | STOP. Follow **Goal-preserving clean pass**; preserve the visible goal and certify ECI only. |
| Disengage without teardown sequence or the applicable final `GetGoal` recheck | STOP. Complete foreground dependencies, resolve known running background tasks, and follow **Goal-preserving clean pass** or **Goal-backed user closure** before `eci-active off` last. For nested ECI, arm or verify the outer ATE guard first. |
| Dependent work launched in background, blocking `TaskOutput` used to await it, or `TaskStop` used as context reset/teardown | STOP. Use foreground `Agent`; reserve notifications/nonblocking snapshots for independent background work and `TaskStop` for exact known running task cancellation. |
| Shell-launched Kimi process used as an agent | STOP. Use foreground `Agent` / `Agent` with `resume`, or independent background `Agent` with notifications; hard-escalate if unavailable. |
| Status report uses task/iteration numbers, or flat-lists nested work | See **Status reports** section. |
| "Fresh context needed" → spawned a separate agent for Step 1 or Step 3 instead of resuming the existing agent | The persistent agent provides fresh context per message via the spawn-prompt baseline. Resume the existing explorer/implementer (`Agent` with `resume`); do not spawn fresh. |
| Critic absorbed CONDITIONALs by rewriting option | STOP. Critic tags only — orchestrator folds CONDITIONALs into the Step 3 resume-message body. |
| Orchestrator forgot to pass Step 2 CONDITIONALs to implementer | STOP. Step 3 message must include verbatim CONDITIONAL fix-list. |
| Submission accepted with untagged factual claims | STOP. Tag-audit failure = REJECT in current gate (per Critic A/B rule). |
| A matching coding-style skill was loaded, but no independent admission exists | STOP. Invocation is not compliance; complete the applicable record and Step 2 admission before durable work. |
| Durable work starts before admission, or affected work continues after scope/source/conflict/deviation drift | STOP affected work. Isolated disposable work may continue under the stated boundary; send local/tool-covered deltas to a fresh foreground `critic-step2` and route substantive drift through Steps 1/2. |
| Empty Style Brief, bare no-source claim, or rule-by-rule style inventory | STOP. Use only the applicable admission route with exact discovery anchors and grouped material decisions. |
| A false correctness, security, RCA, testing/proof/TDD, or approved architecture/ownership/purpose/interface result is labeled a style deviation | STOP. Critic A treats it as the corresponding hard non-style failure. |
| Hook/protocol/reviewer wording claims a heuristic proves, classifies, or determines task nature without matching mechanism evidence and boundary tests | STOP. Reword to the strongest supported claim and add negative/boundary pressure. |
| Code/debugging submission lacks root-cause rationale or required regression explanation | STOP. Bounce before gate; unknown "why" means unsubmittable. |
| Bug RCA prompt lacks regression report path or previous/current test-run evidence packet | STOP. Write/update the report artifact, then resend the RCA assignment. |
| Critic fails to critique root-cause rationale or regression explanation | STOP. Re-prompt or re-spawn critic. |
| Substantive REJECT/CONDITIONAL fixed directly after review gate | STOP. Batch all gate issues and return to Step 1/Step 2 explorer/designer-critic loop. |
| Gate issues handled one-by-one | STOP. Batch by affected artifact/API/contract before re-exploration or implementation. |

## Relationship to other skills

| Skill | Difference |
|-------|-----------|
| `brainstorming` | Explores user intent before design. This skill explores solutions after intent is clear. |
| `agent-teams-execution` | ATE is the outer workflow for large or multi-workstream work. It may route bounded work through ECI; ATE remains outer. ECI borrows ATE's rubber-stamp check: a critic citing no issues beyond producer self-reports must be re-spawned with a harsher prompt. |
| `blocker-resolution-protocol` | Shared blocker handling. ECI keeps its own role separation, loop-breaker, and hard-escalation semantics while using the shared blocker record and escalation rules. |
| `systematic-debugging` | For diagnosing a known bug. This skill is for open-ended improvement/design research. |
| `proof-driven-development` | Proves correctness of logic. This skill selects which logic to build. |
