---
name: npm-supplychain-check
description: Scan this machine for the Miasma / Phantom Gyp ("TeamPCP") npm supply-chain compromise that plants backdoors in Claude Code (~/.claude/settings.json) and VS Code (.vscode/tasks.json). Use when the user asks to check if their PC/machine is infected, compromised, or affected by the npm/Claude Code backdoor attack, credential-stealing worm, or Shai-Hulud campaign.
---

# npm Supply-Chain / Claude Code Backdoor Check

Read-only detection for the credential-stealing campaign that weaponizes the
Claude Code **hooks** feature and VS Code tasks for persistence. The attack
vector is always installing a poisoned npm package — there is no Claude Code
vulnerability itself.

## How to run

```bash
# Default: scan $HOME plus global Claude/shell checks
scripts/scan.sh

# Or scan a specific project tree (global checks still run)
scripts/scan.sh /path/to/project
```

Exit code `0` = clean, `1` = suspicious findings.

## SAFETY — order matters

This script is **read-only**. It never deletes, modifies, or revokes anything.
That is deliberate: the malware contains a dead-man's switch that wipes the home
directory if it detects its access being cut. **If findings appear, do NOT start
by revoking tokens.** Correct order:

1. Screenshot the offending hook/task for evidence.
2. Disconnect the machine from the network.
3. Remove the injected hook/task.
4. Rotate credentials **from a separate, clean machine** — npm tokens, GitHub
   PATs, SSH keys, then cloud (AWS/GCP/Azure), Kubernetes, Vault.

## What it checks

1. **`~/.claude/settings.json`** (+ `.local`) — the primary persistence target;
   flags `SessionStart` hooks or network/exec keywords.
2. **`.vscode/tasks.json`** — flags tasks that auto-run on `folderOpen`.
3. **Project `.claude/settings*.json`** — flags `SessionStart` / exfil hooks.
   (Legitimate `PostToolUse` / `PreToolUse` project hooks are *not* flagged.)
4. **Affected npm packages** — global installs, `node_modules` dirs, and lockfiles
   for the known IoC families (`@redhat-cloud-services`, `@vapi-ai/server-sdk`,
   `ai-sdk-ollama`, `node-env-resolver`, `wrangler-deploy`, `autotel`, `awaitly`,
   `executable-stories`).
5. **Worm artifacts** — `shai-hulud` / `miasma` GitHub workflow files.
6. **Shell rc files** — `curl|wget|base64 -d` piped into a shell, or `/dev/tcp`.

## Interpreting results

- **CLEAN** — no IoCs; no cleanup needed. The user does not need the revoke
  sequence.
- **SUSPICIOUS** — read each flagged file before acting; distinguish your own
  legitimate hooks from injected ones, then follow the order above.

## Hardening to suggest afterward

- `npm config set ignore-scripts true` (relax per-package for native builds).
- Commit `package-lock.json`; use `npm ci` (not `npm install`) in automation.
- Scope CI/CD tokens to least privilege.
