---
name: kimi-crash-recovery
description: Use when Kimi CLI/session has just relaunched after a crash with unfinished work or active spawned agents.
---

# Kimi Crash Recovery

Use only right after crash relaunch; no new crash means out of scope. Resume; do not restart.

1. Reconstruct state from summary, plan, git, ledgers, handovers, and active-mode state. Kimi session transcripts live at `~/.kimi-code/sessions/<workDirKey>/<sessionId>/agents/main/wire.jsonl` (main thread) and `~/.kimi-code/sessions/<workDirKey>/<sessionId>/agents/agent-N/wire.jsonl` (spawned agents).
2. Preserve agent context: resume active agent ids (`Agent` with `resume`), then send exactly `continue` and nothing else; if lost, prompt replacement fully.
3. Continue main-thread work from the last in-progress task.
4. Inspect dirty files before editing.
5. Report resumed/missing agents and current main-thread task.
