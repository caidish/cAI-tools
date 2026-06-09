#!/bin/sh
# npm-supplychain-check / scan.sh
#
# READ-ONLY scan for the Miasma / Phantom Gyp ("TeamPCP") npm supply-chain
# campaign that plants persistence in Claude Code (~/.claude/settings.json)
# and VS Code (.vscode/tasks.json), and harvests credentials.
#
# This script ONLY reads files. It never deletes, revokes, or modifies anything.
# (Revoking tokens before the host is verified clean is the dangerous step the
#  malware weaponizes — so detection must come first.)
#
# Usage:  scan.sh [SCAN_ROOT]
#   SCAN_ROOT defaults to $HOME. Pass a project dir to scan just that tree
#   (the global ~/.claude and shell rc checks always run regardless).
#
# Exit codes: 0 = clean, 1 = suspicious findings (inspect manually).

ROOT="${1:-$HOME}"
FINDINGS=0

# Affected package families from this campaign (not exhaustive — see advisories).
IOC_PKGS='redhat-cloud-services|@vapi-ai|vapi-ai|ai-sdk-ollama|autotel|awaitly|executable-stories|node-env-resolver|wrangler-deploy'
# Commands that have no business inside a Claude Code hook / shell rc one-liner.
EXFIL='curl|wget|base64|eval|/dev/tcp|atob|nc |xxd|openssl enc'

flag() { FINDINGS=$((FINDINGS+1)); printf '  [!] %s\n' "$1"; }
ok()   { printf '  [ok] %s\n' "$1"; }

echo "============================================================"
echo " npm supply-chain / Claude Code backdoor scan"
echo " scan root: $ROOT"
echo "============================================================"

# ---------------------------------------------------------------------------
echo
echo "[1] Global Claude settings (~/.claude/settings*.json) — primary target"
for f in "$HOME/.claude/settings.json" "$HOME/.claude/settings.local.json"; do
  [ -f "$f" ] || { ok "$f not present"; continue; }
  if grep -qiE 'SessionStart' "$f"; then
    flag "$f has a SessionStart hook — inspect (malware persists here)"
  elif grep -qiE "$EXFIL" "$f"; then
    flag "$f contains network/exec keywords ($EXFIL) — inspect"
  else
    ok "$f clean (no SessionStart / exfil patterns)"
  fi
done

# ---------------------------------------------------------------------------
echo
echo "[2] VS Code tasks.json with folderOpen auto-run trigger"
TASKS=$(find "$ROOT" -name tasks.json -path '*.vscode*' 2>/dev/null)
HIT=0
for t in $TASKS; do
  if grep -qi 'folderOpen' "$t"; then flag "$t runs on folderOpen — inspect"; HIT=1; fi
done
[ "$HIT" = 0 ] && ok "no .vscode/tasks.json with folderOpen"

# ---------------------------------------------------------------------------
echo
echo "[3] Project .claude/settings*.json hooks"
SETT=$(find "$ROOT" -path '*/.claude/settings*.json' 2>/dev/null)
HIT=0
for f in $SETT; do
  grep -qi 'hooks' "$f" 2>/dev/null || continue
  if grep -qiE 'SessionStart' "$f"; then
    flag "$f has SessionStart hook — inspect"; HIT=1
  elif grep -qiE "$EXFIL" "$f"; then
    flag "$f hook contains exfil keywords — inspect"; HIT=1
  fi
done
[ "$HIT" = 0 ] && ok "no project settings with SessionStart/exfil hooks (legit PostToolUse/PreToolUse hooks are fine)"

# ---------------------------------------------------------------------------
echo
echo "[4] Affected npm packages"
# 4a: global installs
if command -v npm >/dev/null 2>&1; then
  G=$(npm ls -g --depth=0 2>/dev/null | grep -iE "$IOC_PKGS")
  if [ -n "$G" ]; then flag "global npm: $G"; else ok "no affected global npm packages"; fi
else
  ok "npm not installed"
fi
# 4b: node_modules dirs
NM=$(find "$ROOT" -type d -path '*node_modules/*' \( \
      -path '*node_modules/@redhat-cloud-services*' -o \
      -path '*node_modules/@vapi-ai*' -o \
      -name 'ai-sdk-ollama' -o -name 'node-env-resolver' -o \
      -name 'wrangler-deploy' -o -name 'autotel' -o -name 'awaitly' \) 2>/dev/null | head -20)
if [ -n "$NM" ]; then flag "affected dirs in node_modules:"; printf '      %s\n' $NM; else ok "no affected packages in any node_modules"; fi
# 4c: lockfiles
LF=0
for lock in $(find "$ROOT" \( -name package-lock.json -o -name yarn.lock -o -name pnpm-lock.yaml \) -not -path '*/node_modules/*' 2>/dev/null); do
  if grep -qiE "$IOC_PKGS" "$lock" 2>/dev/null; then flag "lockfile references affected pkg: $lock"; LF=1; fi
done
[ "$LF" = 0 ] && ok "no lockfiles reference affected packages"

# ---------------------------------------------------------------------------
echo
echo "[5] Worm artifacts (Shai-Hulud / Miasma GitHub workflows)"
WF=$(find "$ROOT" -path '*.github/workflows*' \( -iname '*shai*' -o -iname '*hulud*' -o -iname '*miasma*' \) 2>/dev/null)
if [ -n "$WF" ]; then flag "worm workflow files:"; printf '      %s\n' $WF; else ok "no shai-hulud/miasma workflow files"; fi

# ---------------------------------------------------------------------------
echo
echo "[6] Shell rc files piping remote content into a shell"
HIT=0
for rc in "$HOME/.zshrc" "$HOME/.bashrc" "$HOME/.bash_profile" "$HOME/.profile" "$HOME/.zprofile"; do
  [ -f "$rc" ] || continue
  if grep -nEi 'curl .*\| *(sh|bash)|wget .*\| *(sh|bash)|base64 .*-d.*\| *(sh|bash)|/dev/tcp' "$rc" >/dev/null 2>&1; then
    flag "suspicious one-liner in $rc:"; grep -nEi 'curl .*\| *(sh|bash)|wget .*\| *(sh|bash)|base64 .*-d.*\| *(sh|bash)|/dev/tcp' "$rc"; HIT=1
  fi
done
[ "$HIT" = 0 ] && ok "no curl|base64 -> shell pipes in shell rc files"

# ---------------------------------------------------------------------------
echo
echo "============================================================"
if [ "$FINDINGS" -eq 0 ]; then
  echo " RESULT: CLEAN — no indicators of compromise found."
  echo "============================================================"
  exit 0
else
  echo " RESULT: $FINDINGS SUSPICIOUS finding(s) — DO NOT panic-revoke."
  echo " Order: 1) screenshot evidence  2) disconnect network"
  echo "        3) remove injected hook/task  4) rotate creds from a"
  echo "        CLEAN machine (npm, GitHub PAT, SSH, then cloud keys)."
  echo "============================================================"
  exit 1
fi
