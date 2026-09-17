---
name: codex
description: Use when the user asks to run Codex CLI (codex exec, codex resume) or references OpenAI Codex for code analysis, code review, or automated editing
---

# Codex Skill Guide

Requires Codex CLI 0.153+ (`codex --version`). `--full-auto` no longer exists in this line; use `--approve-for-me`.

## Models and Reasoning Effort

| Model | Tier | Use for |
| --- | --- | --- |
| `gpt-6-astra` | Flagship (default) | Hardest end-to-end work: architecture, multi-file refactors, security review, long agentic runs. ~1M context. |
| `gpt-5.6-sol` | GPT-5.6 flagship | Complex agentic coding when Astra is unavailable or over budget |
| `gpt-5.6-terra` | Mid tier | Everyday feature work, bug fixes, tests, routine review (GPT-5.5 class, cheaper) |
| `gpt-5.6-luna` | Fast, cheapest | Quick edits, lint, docs, formatting, throwaway or high-volume calls |

Effort ladder for `model_reasoning_effort`: `low` < `medium` < `high` < `xhigh` < `max` (provider also accepts `none`, `minimal`).
- Default `xhigh`. `max` is for astra/sol on genuinely hard problems; it is slow and token-heavy.
- Suggested pairing: astra/sol `xhigh` or `max`; terra `medium`/`high`; luna `low`/`medium`.
- Astra at `low` roughly matches Sol at `high`; do not raise effort by default.
- `ultra` (parallel internal sub-agents) is accepted by astra/sol on some builds but is not in the provider's validated list. Use only on explicit request; on an `invalid_value` error fall back to `max`.

## Running a Task
1. If the user already named a model and effort, use them. Otherwise ask once via `AskUserQuestion` with **two questions in a single prompt**: model (`gpt-6-astra` (Recommended), `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`) and effort (`xhigh` (Recommended), `high`, `medium`, `max`). Pre-select per the table above based on task difficulty.
2. Pick the sandbox. Default `--sandbox read-only`. For edits: `--sandbox workspace-write --approve-for-me`. Add `-c sandbox_workspace_write.network_access=true` when the task needs network inside workspace-write. `--sandbox danger-full-access` only with explicit permission.
3. Assemble:
   ```bash
   echo "<PROMPT>" | codex exec --skip-git-repo-check -m <MODEL> -c model_reasoning_effort="<EFFORT>" --sandbox <MODE> [-C <DIR>] [--add-dir <DIR>] [-i <IMAGE>] [-o <FILE>] [--ephemeral] - 2>/dev/null
   ```
   - Always `--skip-git-repo-check`. Always `2>/dev/null` (hides thinking tokens on stderr) unless the user asks for them or you are debugging.
   - `-o <FILE>` writes only the final message; use it when you must parse the answer. `--ephemeral` for throwaway runs that need not be resumable.
   - Pass `timeout: 600000` or more to Bash; astra/sol at `xhigh`/`max` can run many minutes.
4. Run, capture stdout, summarize the outcome.
5. Then tell the user: "You can resume this Codex session at any time by saying 'codex resume' or asking me to continue with additional analysis or changes."

### Quick Reference
| Use case | Command shape |
| --- | --- |
| Read-only review or analysis | `--sandbox read-only 2>/dev/null` |
| Apply local edits | `--sandbox workspace-write --approve-for-me 2>/dev/null` |
| Edits plus network | `--sandbox workspace-write --approve-for-me -c sandbox_workspace_write.network_access=true 2>/dev/null` |
| Broad access | `--sandbox danger-full-access --approve-for-me 2>/dev/null` (ask first) |
| Review uncommitted changes | `codex exec review --uncommitted --skip-git-repo-check -m <MODEL> -c model_reasoning_effort="<EFFORT>" 2>/dev/null` (no custom prompt allowed with `--uncommitted`, `--base`, or `--commit`) |
| Review vs branch / a commit | `codex exec review --base <BRANCH> ...` or `codex exec review --commit <SHA> ...` |
| Review with custom instructions | `(echo "Review the following uncommitted diff. <INSTRUCTIONS>"; git diff) \| codex exec --skip-git-repo-check --sandbox read-only -m <MODEL> -c model_reasoning_effort="<EFFORT>" - 2>/dev/null` |
| Resume recent session | `echo "prompt" \| codex exec --skip-git-repo-check resume --last - 2>/dev/null` |
| Run from another directory | add `-C <DIR>` |

## Resuming
- `echo "new prompt" | codex exec --skip-git-repo-check resume --last - 2>/dev/null`. Global flags go between `exec` and `resume`; `--last`, `--all`, `-c` go after `resume`.
- The resumed session inherits model, effort, and sandbox. Do not pass overrides unless the user asks; `resume` has no `-m`, so change the model with `-c model="<MODEL>"` and effort with `-c model_reasoning_effort="<EFFORT>"`.
- Add `--all` after `resume` if the original session started in a different directory.

## Following Up
- After every `codex` command, use `AskUserQuestion` to confirm next steps, collect clarifications, or decide whether to resume.
- Restate the chosen model, effort, and sandbox when proposing follow-up actions.

## Error Handling
- Stop and report when `codex --version` or any `codex exec` exits non-zero; ask for direction before retrying.
- Before using `--approve-for-me`, `--sandbox danger-full-access`, or `--dangerously-bypass-approvals-and-sandbox`, ask permission via `AskUserQuestion` unless already given.
- On `invalid_value` for `reasoning.effort`, rerun with the next lower effort in the ladder.
- When output includes warnings or partial results, summarize them and ask how to adjust.
