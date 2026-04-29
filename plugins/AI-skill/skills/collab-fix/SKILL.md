---
name: collab-fix
description: Collaborative multi-agent fix workflow using codex, gemini-cli, and an independent subagent. Use when the user asks to "collab fix", "multi-agent fix", or wants several AI tools to jointly analyze and fix a bug or task with cross-review.
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
  - Grep
  - Glob
  - Agent
  - AskUserQuestion
---

# Collaborative Multi-Agent Fix

Fix the user's task using **codex**, **gemini-cli**, and an independent subagent in coordinated rounds.

## Requirements
- The `codex` and `gemini-cli` skills must be available. If missing, report the error and stop.
- A `code-reviewer` subagent if available; otherwise use the `general-purpose` agent.
- Expand the user's task into a concise problem description that all agents can act on. Do **not** reinterpret the user's wording — preserve it verbatim alongside your expansion.

## Constraints
- Always run codex and gemini-cli in **read-only** mode. For codex: `--sandbox read-only`. For gemini-cli: do NOT pass `--yolo` or `-s`.
- **Timeout**: pass `timeout: 600000` (10 min) when calling Bash for codex/gemini commands.

## Workflow

1. **Propose plans in parallel.** Ask codex, gemini-cli, and a subagent to analyze the problem and propose fix plans:
   - codex: `echo "Analyze <description>. Propose a fix plan with steps and tradeoffs." | codex exec --skip-git-repo-check --sandbox read-only - 2>/dev/null`
   - gemini-cli: `gemini "Analyze <description>. Propose a fix plan with steps and tradeoffs." -o json 2>/dev/null | jq -r '.response'`
   - subagent: launch an appropriate agent (prefer `code-reviewer`) to analyze independently

2. **Compare and choose.** Summarize tradeoffs across the 3 plans. Ask the user only the **necessary** clarifying questions via `AskUserQuestion` to pick the best fix.

3. **Implement.** Ultrathink and implement the fix yourself. Do **not** git commit.

4. **Cross-review the diff in parallel.**
   - codex: `(echo "Review the following uncommitted diff."; git diff) | codex exec --skip-git-repo-check --sandbox read-only - 2>/dev/null`
   - gemini-cli: `(echo "Review the following uncommitted diff."; git diff) | gemini -o json 2>/dev/null | jq -r '.response'`
   - subagent: launch a code-review agent on the diff

5. **Resolve feedback.** If any item depends on human preference, ask the user via `AskUserQuestion`.

6. **Iterate.** Repeat steps 3–5 until all three reviewers are satisfied, or **5 rounds** are reached. If no consensus after 5 rounds, report the root cause and what remains disputed.
