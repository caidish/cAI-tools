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

To regression-check the detector itself after editing `scan.sh`, run the
synthetic-fixture suite: `sh tests/selftest.sh` (exit `0` = all checks pass).

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
4. **Affected npm packages** — global installs, `node_modules` dirs, and lockfiles.
   Two tiers, because matching a package *name* is not the same as proving compromise:
   - `[!]` **Malicious names** (`ai-sdk-ollama`, `node-env-resolver`, `wrangler-deploy`,
     `autotel`, `awaitly`, `executable-stories`) — the package itself is the malware;
     a match is a real IoC and counts toward the suspicious exit code.
   - `[?]` **Targeted scopes** (`@redhat-cloud-services`, `@vapi-ai`) — legitimate,
     widely-used scopes where only specific poisoned *versions* were bad. A match is
     surfaced for **version review**, not hard-flagged, so a clean install of Red Hat
     or Vapi packages doesn't trigger a false alarm. Confirm the installed version
     against the advisory before acting.
5. **Worm artifacts** — `shai-hulud` / `miasma` GitHub workflow files.
6. **Shell rc files** — `curl|wget|base64 -d` piped into a shell, or `/dev/tcp`.
7. **`npm audit`** (only when scanning a single project with a `package.json`) —
   a database lookup against published advisories. This is **complementary**, not
   redundant: checks 1–6 catch the *persistence backdoor* and known *names* that
   audit can't see, while audit is **version-precise and auto-updating** — it
   confirms a known-bad *installed version* and stays current as new advisories
   land, which a frozen hardcoded list cannot. It is blind to zero-days (it found
   nothing during this campaign's first hours) and to the config backdoor, so it
   never stands alone. Read-only locally; we never run `npm audit fix`. Audit hits
   that name a campaign family are hard `[!]` findings; overall critical/high
   counts are surfaced as `[i]` general hygiene, not campaign signal.

## Interpreting results

- **CLEAN** — no IoCs; no cleanup needed. The user does not need the revoke
  sequence.
- **CLEAN of hard IoCs + `[?]` review items** — a legitimate-but-targeted scope
  was found. Exit code is still `0`. Check the installed version against the
  advisory's bad-version list; only escalate if it matches.
- **SUSPICIOUS** (`[!]`) — read each flagged file before acting; distinguish your
  own legitimate hooks from injected ones, then follow the order above.

## Hardening to suggest afterward

- `npm config set ignore-scripts true` (relax per-package for native builds).
- Commit `package-lock.json`; use `npm ci` (not `npm install`) in automation.
- Scope CI/CD tokens to least privilege.
