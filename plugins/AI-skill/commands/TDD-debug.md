# TDD Debug Protocol

You must debug $ARGUMENTS using a **Test-Driven Development** approach combined with the **collab-fix** protocol.

## Overview
This workflow ensures bugs are fixed with proper test coverage by:
1. First writing a **failing** test that reproduces the bug
2. Then fixing the bug using multi-agent collaboration
3. Verifying the test passes after the fix

## Requirements:
- a code-reviewer subagent. If not, use general-purpose Task tool.
- a test-automator subagent for test design review.

## Constraints:
- **Timeout**: Always use `timeout: 1200000` (20 min) when calling Bash for codex/gemini commands.
- The test MUST fail before the fix and MUST pass after the fix.
---

## Phase 1: Reproduce the Bug with a Failing Test

### Step 1.1: Analyze the Bug
First, expand the bug description to add context. Don't interpret $ARGUMENTS on your own but copy it verbatim. Gather information about:
- The expected behavior
- The actual (buggy) behavior
- The relevant code paths
- The testing framework used in the project

### Step 1.2: Design the Test
Ask **codex**, **gemini-cli**, and a **test-automator subagent** in parallel to propose a test that reproduces the bug:
- **codex**: `echo "Given this bug: ""$ARGUMENTS"". Design a test case that will FAIL when the bug exists and PASS when fixed. Include the test code and explain why it catches this bug." | codex exec --skip-git-repo-check --sandbox read-only - 2>/dev/null`
- **gemini-cli**: `gemini "Given this bug: ""$ARGUMENTS"". Design a test case that will FAIL when the bug exists and PASS when fixed. Include the test code and explain why it catches this bug." -o json 2>/dev/null | jq -r '.response'`
- **subagent**: Launch a test-automator agent to independently design a reproducing test

### Step 1.3: Select and Implement the Test
1. Compare the 3 proposed tests and summarize their approaches.
2. Ask the user which test approach to use (use `AskUserQuestion`).
3. Implement the chosen test in the appropriate test file.

### Step 1.4: Verify the Test Fails
1. Run the test to confirm it **FAILS** (proving the bug exists).
2. Use `AskUserQuestion` to ask the user:
   - "Does the test correctly reproduce the bug?"
   - "Does the test failure match the expected buggy behavior?"
   - "Is the test implementation acceptable?"
3. If the user rejects the test, iterate on test design (return to Step 1.2).
4. **Do not proceed to Phase 2 until the user confirms the test is valid.**

---

## Phase 2: Fix the Bug (Collab-Fix Protocol with Test Verification)

### Step 2.1: Propose Fix Plans
Ask **codex**, **gemini-cli**, and a **code-reviewer subagent** in parallel to analyze and propose fixes:
- **codex**: `echo "Analyze this bug: ""$ARGUMENTS"". We have a failing test that reproduces it. Propose a fix plan with steps and tradeoffs. The fix must make the test pass." | codex exec --skip-git-repo-check --sandbox read-only - 2>/dev/null`
- **gemini-cli**: `gemini "Analyze this bug: ""$ARGUMENTS"". We have a failing test that reproduces it. Propose a fix plan with steps and tradeoffs. The fix must make the test pass." -o json 2>/dev/null | jq -r '.response'`
- **subagent**: Launch a code-reviewer agent to propose a fix independently

### Step 2.2: Select Fix Approach
Compare the 3 plans, summarize tradeoffs, and ask the user only the **necessary** questions to choose the best fix (use `AskUserQuestion`).

### Step 2.3: Implement the Fix
Ultrathink: implement the fix (must not git commit) on your own.

### Step 2.4: Verify Test Passes
1. Run the reproducing test to confirm it now **PASSES**.
2. If the test still fails, analyze why and iterate on the fix.

### Step 2.5: Review the Changes
Ask **codex**, **gemini-cli**, and **subagents** to review the uncommitted changes, specifically checking:
- Code correctness
- Test feasibility and quality
- That the test genuinely validates the fix (not a false positive)

Run in parallel:
- **codex**: `(echo "Review the following uncommitted diff. Verify: 1) The fix is correct, 2) The test is feasible and properly validates the fix, 3) No regressions introduced."; git diff) | codex exec --skip-git-repo-check --sandbox read-only - 2>/dev/null`
- **gemini-cli**: `(echo "Review the following uncommitted diff. Verify: 1) The fix is correct, 2) The test is feasible and properly validates the fix, 3) No regressions introduced."; git diff) | gemini -o json 2>/dev/null | jq -r '.response'`
- **subagent**: Launch a code-reviewer agent to review the diff with focus on test validity

### Step 2.6: Iterate if Needed
1. Review their responses; if any item depends on human preference, ask the user (use `AskUserQuestion`).
2. Repeat steps 2.3–2.5 until:
   - All three reviewers are satisfied, AND
   - The test passes
   - OR **5 rounds** reached

If no consensus after 5 rounds, report:
- The root cause of the bug
- What remains disputed
- Whether the test is passing or failing
- Recommendations for resolution

---

## Summary Output
After completion, provide a summary including:
1. **Bug Description**: The original bug
2. **Test Created**: Location and description of the reproducing test
3. **Fix Applied**: Summary of the changes made
4. **Test Status**: Confirmation that the test now passes
5. **Review Consensus**: Final reviewer feedback

---

