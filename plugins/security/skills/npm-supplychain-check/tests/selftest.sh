#!/bin/sh
# Self-test for scan.sh — builds SYNTHETIC fixtures that exercise each detection
# path and asserts the scanner reacts correctly. These are constructed positives,
# not real malware; they verify the *logic* (regexes match, tiers route, spaces
# in paths don't break iteration), so future edits to scan.sh stay regression-safe.
#
# Run:  sh tests/selftest.sh      (exit 0 = all pass, 1 = a check failed)
set -u

HERE=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
SCAN="$HERE/scripts/scan.sh"
PASS=0; FAIL=0
T=$(mktemp -d)
export HOME="$T/home"; mkdir -p "$HOME"   # isolate global checks → deterministic
trap 'rm -rf "$T"' EXIT

check() {   # desc, expected-substring, output
  if printf '%s' "$3" | grep -qF "$2"; then PASS=$((PASS+1)); printf 'ok   - %s\n' "$1"
  else FAIL=$((FAIL+1)); printf 'FAIL - %s (missing: %s)\n' "$1" "$2"; fi
}
checkrc() { # desc, expected-exit, actual-exit
  if [ "$2" = "$3" ]; then PASS=$((PASS+1)); printf 'ok   - %s (exit %s)\n' "$1" "$3"
  else FAIL=$((FAIL+1)); printf 'FAIL - %s (want exit %s, got %s)\n' "$1" "$2" "$3"; fi
}

# 1) spaced-path .vscode/tasks.json with folderOpen — guards the IFS/word-split fix
P="$T/proj with space"; mkdir -p "$P/.vscode"
printf '{"tasks":[{"runOptions":{"runOn":"folderOpen"}}]}\n' > "$P/.vscode/tasks.json"
OUT=$(sh "$SCAN" "$P"); RC=$?
check   "folderOpen task under a spaced path is flagged" "runs on folderOpen" "$OUT"
checkrc "spaced-path fixture exits suspicious"           1 "$RC"

# 2) malicious package NAME in a lockfile — hard [!] finding
P="$T/mal"; mkdir -p "$P"
printf '{"packages":{"node_modules/wrangler-deploy":{}}}\n' > "$P/package-lock.json"
OUT=$(sh "$SCAN" "$P"); RC=$?
check   "malicious lockfile name is hard-flagged" "lockfile references malicious pkg" "$OUT"
checkrc "malicious fixture exits suspicious"      1 "$RC"

# 3) targeted-but-legit scope ONLY — [?] review, NOT a hard fail
P="$T/scope"; mkdir -p "$P"
printf '{"packages":{"node_modules/@redhat-cloud-services/x":{"version":"1.0.0"}}}\n' > "$P/package-lock.json"
OUT=$(sh "$SCAN" "$P"); RC=$?
check   "targeted scope is review, not flag"   "verify version" "$OUT"
checkrc "scope-only fixture exits clean (0)"   0 "$RC"

# 4) project .claude/settings.json with a SessionStart hook — hard [!] finding
P="$T/hook"; mkdir -p "$P/.claude"
printf '{"hooks":{"SessionStart":[{"command":"echo x"}]}}\n' > "$P/.claude/settings.json"
OUT=$(sh "$SCAN" "$P"); RC=$?
check   "project SessionStart hook is flagged" "SessionStart hook" "$OUT"
checkrc "hook fixture exits suspicious"        1 "$RC"

# 5) clean project — CLEAN result, exit 0
P="$T/clean"; mkdir -p "$P"
printf '{"name":"c","version":"1.0.0"}\n' > "$P/package.json"
OUT=$(sh "$SCAN" "$P"); RC=$?
check   "clean tree reports CLEAN" "RESULT: CLEAN" "$OUT"
checkrc "clean fixture exits 0"    0 "$RC"

echo "-----"
printf '%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
