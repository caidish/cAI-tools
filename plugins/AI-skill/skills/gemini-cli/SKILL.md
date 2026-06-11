---
name: gemini-cli
description: Wield Google's Gemini CLI as a powerful auxiliary tool for code generation, review, analysis, and web research. Use when tasks benefit from a second AI perspective, current web information via Google Search, codebase architecture analysis, or parallel code generation. Also use when user explicitly requests Gemini operations.
allowed-tools:
  - Bash
  - Read
  - Write
  - Grep
  - Glob
---

# Gemini CLI Skill Guide

## When to Use Gemini

| Use Case | Why Gemini |
| --- | --- |
| Current web information | `google_web_search` - real-time Google Search |
| Codebase architecture analysis | `codebase_investigator` - deep analysis tool |
| Second opinion / code review | Different AI perspective catches different bugs |
| Parallel code generation | Offload tasks while continuing other work |

**When NOT to use**: Simple quick tasks (overhead not worth it), interactive refinement, context already understood.

## Running a Task

1. Verify installation: `command -v gemini`
2. Select the mode required for the task; default to read-only (no `--yolo`) unless edits are necessary.
3. **Always use `AskUserQuestion` before using `--yolo` or `-s` flags.** These modes allow file writes or sandboxed execution - get explicit user approval first.
4. Assemble the command with appropriate options:
   - `-m, --model <MODEL>` - Model selection
   - `-y, --yolo` - Auto-approve all tool calls (enables writes)
   - `-s, --sandbox` - Run in Docker isolation
   - `-o, --output-format <text|json>` - Output format
5. **Important**: extract the JSON response with:
   ```bash
   gemini "prompt" -o json 2>/dev/null | perl -0777 -pe 's/^[^{]*//s' | jq -r '.response'
   ```
   The `perl` stage is required: gemini CLI (>= 0.37) prints status noise (e.g. `MCP issues detected. Run /mcp list for status.`) on **stdout** before the JSON object, so piping straight to `jq` fails with `Invalid numeric literal`. The perl filter strips everything before the first `{`.

### Critical Note
YOLO mode does NOT prevent planning prompts. Use forceful language: "Apply now", "Start immediately", "Do this without asking for confirmation".

## Quick Reference

`EXTRACT` below stands for `perl -0777 -pe 's/^[^{]*//s' | jq -r '.response'` (always write it out in full when running commands).

| Use case | Mode | Command pattern |
| --- | --- | --- |
| Read-only analysis | read-only | `gemini "..." -o json 2>/dev/null \| EXTRACT` |
| Apply local edits | write | `gemini "..." --yolo -o json 2>/dev/null \| EXTRACT` |
| Sandboxed write | sandbox | `gemini "..." --yolo --sandbox -o json 2>/dev/null \| EXTRACT` |

### Example Commands

```bash
# Read-only
gemini "Review src/ for bugs" -o json 2>/dev/null | perl -0777 -pe 's/^[^{]*//s' | jq -r '.response'

# Write mode
gemini "Fix bug in file.py. Apply now." --yolo -o json 2>/dev/null | perl -0777 -pe 's/^[^{]*//s' | jq -r '.response'

# If redirection fails, wrap in bash -lc
bash -lc 'gemini "prompt" -o json 2>/dev/null | perl -0777 -pe "s/^[^{]*//s" | jq -r ".response"'
```

## Following Up

- Resume: `echo "follow-up" | gemini -r latest -o json 2>/dev/null | perl -0777 -pe 's/^[^{]*//s' | jq -r '.response'`
- List sessions: `gemini --list-sessions`

## Error Handling

- **jq parse error** (`Invalid numeric literal`): stdout noise before the JSON — make sure the `perl -0777 -pe 's/^[^{]*//s'` stage is in the pipe.
- **Rate limit**: CLI auto-retries with backoff. Use `-m gemini-2.5-flash` for lower priority tasks.
- **Command failure**: Check with `gemini --version`, use `--debug` for details.
- **Always validate** Gemini's output for security vulnerabilities (XSS, injection) before using.
