---
name: TDD-debug
description: Test-Driven Development debug workflow combined with multi-agent collab-fix. Use when the user asks to "TDD debug", "reproduce and fix with a test", or wants a bug fixed with a failing test written first and verified after the fix.
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

# TDD Debug Protocol

Debug the user's bug using a **Test-Driven Development** approach combined with the **collab-fix** protocol.

## Overview
1. Write a **failing** test that reproduces the bug.
2. Fix the bug using multi-agent collaboration.
3. Verify the test passes after the fix.

## Requirements
- A `code-reviewer` subagent if available; otherwise use the `general-purpose` agent.
- A `test-automator` subagent for test design review if available; otherwise use the `general-purpose` agent.

## Constraints
- **Timeout**: pass `timeout: 1200000` (20 min) when calling Bash for codex/gemini commands.
- The test MUST fail before the fix and MUST pass after the fix.
- Preserve the user's bug description verbatim alongside any expansion you add.

---

## Phase 1: Reproduce the Bug with a Failing Test

### 1.1 Analyze the Bug
Expand the bug description with context: expected behavior, actual (buggy) behavior, relevant code paths, the project's testing framework. Keep the user's wording verbatim alongside your notes.

### 1.2 Design the Test (parallel)
Ask codex, gemini-cli, and a `test-automator` subagent to each propose a reproducing test:
- codex: `echo "Given this bug: <description>. Design a test case that will FAIL when the bug exists and PASS when fixed. Include the test code and explain why it catches this bug." | codex exec --skip-git-repo-check --sandbox read-only - 2>/dev/null`
- gemini-cli: `gemini "Given this bug: <description>. Design a test case that will FAIL when the bug exists and PASS when fixed. Include the test code and explain why it catches this bug." -o json 2>/dev/null | jq -r '.response'`
- subagent: launch a test-automator agent to independently design a reproducing test

### 1.3 Select and Implement
1. Compare the 3 proposals and summarize approaches.
2. Use `AskUserQuestion` to let the user pick.
3. Implement the chosen test in the appropriate test file.

### 1.4 Verify the Test Fails
1. Run the test to confirm it **FAILS** (proving the bug exists).
2. Use `AskUserQuestion`:
   - Does the test correctly reproduce the bug?
   - Does the failure match the expected buggy behavior?
   - Is the test implementation acceptable?
3. If the user rejects the test, iterate (return to 1.2).
4. **Do not proceed to Phase 2 until the user confirms the test is valid.**

---

## Phase 2: Fix the Bug (collab-fix with test verification)

### 2.1 Propose Fix Plans (parallel)
- codex: `echo "Analyze this bug: <description>. We have a failing test that reproduces it. Propose a fix plan with steps and tradeoffs. The fix must make the test pass." | codex exec --skip-git-repo-check --sandbox read-only - 2>/dev/null`
- gemini-cli: `gemini "Analyze this bug: <description>. We have a failing test that reproduces it. Propose a fix plan with steps and tradeoffs. The fix must make the test pass." -o json 2>/dev/null | jq -r '.response'`
- subagent: launch a `code-reviewer` agent to propose a fix independently

### 2.2 Select Fix
Compare the 3 plans, summarize tradeoffs, and ask the user only the **necessary** questions via `AskUserQuestion`.

### 2.3 Implement
Ultrathink and implement the fix yourself. Do **not** git commit.

### 2.4 Verify Test Passes
Run the reproducing test. If it still fails, analyze and iterate.

### 2.5 Cross-Review (parallel)
- codex: `(echo "Review the following uncommitted diff. Verify: 1) The fix is correct, 2) The test is feasible and properly validates the fix, 3) No regressions introduced."; git diff) | codex exec --skip-git-repo-check --sandbox read-only - 2>/dev/null`
- gemini-cli: `(echo "Review the following uncommitted diff. Verify: 1) The fix is correct, 2) The test is feasible and properly validates the fix, 3) No regressions introduced."; git diff) | gemini -o json 2>/dev/null | jq -r '.response'`
- subagent: launch a `code-reviewer` agent focused on test validity

### 2.6 Iterate
Resolve human-preference items via `AskUserQuestion`. Repeat 2.3–2.5 until all three reviewers are satisfied AND the test passes, or **5 rounds** are reached.

If no consensus after 5 rounds, report:
- Root cause of the bug
- Remaining disputed items
- Whether the test is passing or failing
- Recommendations for resolution

---

## Summary Output
After completion, report:
1. **Bug description** (original)
2. **Test created** — location and purpose
3. **Fix applied** — summary of the changes
4. **Test status** — confirmation it now passes
5. **Review consensus** — final reviewer feedback
