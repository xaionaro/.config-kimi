# Kimi Tool Mapping

Skills in this collection use Kimi tool names natively. When you encounter legacy references in an unported skill or older document, use the Kimi equivalent:

| Legacy reference | Kimi equivalent |
|------------------|------------------|
| Legacy subagent dispatch (`spawn_agent`, `Task`) | `Agent` tool with `subagent_type` (see [Named agent dispatch](#named-agent-dispatch)) |
| Legacy parallel dispatches | Multiple `Agent` calls in one message, or `AgentSwarm` for same-template fan-out |
| Legacy follow-up to a live agent (`send_input`) | `Agent` with `resume: <agent id>` |
| Legacy subagent result (`wait_agent`) | `TaskOutput` (use `block: true` to wait) |
| Legacy fire-and-forget cleanup (`close_agent`) | `TaskStop` to free the slot |
| `update_plan` (task tracking) | `TodoList` |
| `apply_patch` | `Edit` / `Write` |
| `shell` / `exec_command` | `Bash` |
| `WebFetch` | `FetchURL` |
| `Skill` tool (invoke a skill) | Skills load natively — just follow the instructions; manual invocation: `/skill:<name>` |
| `Read`, `Write`, `Edit` (files) | Same names natively |
| `Bash` (run commands) | Same name natively |

## Subagent dispatch

The `Agent` tool is built in — no config flag is required. Available `subagent_type` values:

| `subagent_type` | Purpose |
|-----------------|---------|
| `coder` | Default. Full tools — implementation, file edits, commands |
| `explore` | Read-only codebase research and review |
| `plan` | Read-only implementation planning |

Agent lifecycle:

- **Reuse an agent:** pass its id via `resume` — `Agent(resume: <agent id>, prompt: ...)` starts a new turn with the agent's prior context kept. There is no context-clear for a resumed agent; for a clean context, `TaskStop` and respawn under the same role label.
- **Wait for an agent:** `TaskOutput` with `block: true` (default timeout 30s; raise `timeout` for long waits). A non-blocking `TaskOutput` call returns a status/output snapshot.
- **Stop an agent:** `TaskStop`.
- **Background/parallel work:** launch with `run_in_background: true`; completion arrives as a notification — do not poll with blocking calls right after launching.

## Named agent dispatch

Legacy compatibility references may name agent types with old namespaces like `superpowers:code-reviewer`.
Kimi does not have a named agent registry — `Agent` creates agents from the built-in subagent types (`coder`, `explore`, `plan`).

When a skill says to dispatch a named agent type:

1. Find the agent's prompt file (e.g., `agents/code-reviewer.md` or the skill's
   local prompt template like `code-quality-reviewer-prompt.md`)
2. Read the prompt content
3. Fill any template placeholders (`{BASE_SHA}`, `{WHAT_WAS_IMPLEMENTED}`, etc.)
4. Spawn a `coder` agent with the filled content as the `prompt`

| Skill instruction | Kimi equivalent |
|-------------------|------------------|
| compat reference: Legacy named `code-reviewer` dispatch | `Agent(subagent_type="coder", prompt=...)` with `code-reviewer.md` content |
| compat reference: Legacy inline subagent dispatch | `Agent(prompt=...)` with the same prompt |

### Message framing

The `prompt` parameter is user-level input, not a system prompt. Structure it
for maximum instruction adherence:

```
Your task is to perform the following. Follow the instructions below exactly.

<agent-instructions>
[filled prompt content from the agent's .md file]
</agent-instructions>

Execute this now. Output ONLY the structured response following the format
specified in the instructions above.
```

- Use task-delegation framing ("Your task is...") rather than persona framing ("You are...")
- Wrap instructions in XML tags — the model treats tagged blocks as authoritative
- End with an explicit execution directive to prevent summarization of the instructions

### Why the workaround stays

Kimi has no named agent registry or skill-side `agents` manifest field, so
dispatching a "named" agent always means reading its prompt file and passing
the filled content to a built-in subagent type. This is the stable mechanism,
not a stopgap.

## Environment Detection

Branch and PR workflows should detect their environment with read-only git
commands before proceeding:

```bash
GIT_DIR=$(cd "$(git rev-parse --git-dir)" 2>/dev/null && pwd -P)
GIT_COMMON=$(cd "$(git rev-parse --git-common-dir)" 2>/dev/null && pwd -P)
BRANCH=$(git branch --show-current)
```

- `GIT_DIR != GIT_COMMON` → already in a linked worktree
- `BRANCH` empty → detached HEAD (cannot branch/push/PR from this session)

See `finishing-a-development-branch` Step 1 for how that skill uses these
signals.

## Externally Managed Worktrees

When the environment blocks branch/push operations (detached HEAD in an
externally managed worktree), the agent commits all work and hands the
remaining git operations to the user.

The agent can still run tests, stage files, and output suggested branch
names, commit messages, and PR descriptions for the user to copy.
