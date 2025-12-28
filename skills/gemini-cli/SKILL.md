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
3. Assemble the command with appropriate options:
   - `-m, --model <MODEL>` - Model selection
   - `-y, --yolo` - Auto-approve all tool calls (enables writes)
   - `-s, --sandbox` - Run in Docker isolation
   - `-o, --output-format <text|json>` - Output format
4. **IMPORTANT**: Append `2>/dev/null` to all gemini commands to suppress thinking tokens (stderr). Only show stderr if debugging is needed.

### Critical Note
YOLO mode does NOT prevent planning prompts. Use forceful language: "Apply now", "Start immediately", "Do this without asking for confirmation".

## Quick Reference

| Use case | Mode | Key flags |
| --- | --- | --- |
| Read-only analysis / review | read-only | `-o text 2>/dev/null` |
| Web search | read-only | `-o text 2>/dev/null` |
| Codebase architecture | read-only | `-o text 2>/dev/null` |
| Apply local edits | write | `--yolo -o text 2>/dev/null` |
| Sandboxed write | sandbox | `--yolo --sandbox -o text 2>/dev/null` |
| Background long task | write | `--yolo -o text 2>&1 &` |

### Example Commands

```bash
# Read-only code review (will prompt if attempting writes)
gemini "Review src/ for bugs and security issues" -o text 2>/dev/null

# Read-only web search
gemini "What are the latest React 19 features? Use Google Search." -o text 2>/dev/null

# Read-only codebase analysis
gemini "Use codebase_investigator to analyze this project" -o text 2>/dev/null

# Write mode - code generation
gemini "Create [description]. Start immediately." --yolo -o text 2>/dev/null

# Write mode - bug fix
gemini "Fix [issue] in [file]. Apply now." --yolo -o text 2>/dev/null

# Sandboxed write mode (Docker isolation)
gemini "Run tests and fix failures." --yolo --sandbox -o text 2>/dev/null
```

## Following Up

- Use session resume for multi-turn workflows: `echo "follow-up" | gemini -r latest -o text 2>/dev/null`
- List sessions: `gemini --list-sessions`
- For long tasks, run in background and monitor with `TaskOutput`

## Error Handling

- **Rate limit**: CLI auto-retries with backoff. Use `-m gemini-2.5-flash` for lower priority tasks.
- **Command failure**: Check with `gemini --version`, use `--debug` for details.
- **Always validate** Gemini's output for security vulnerabilities (XSS, injection) before using.
