#!/usr/bin/env python3
"""
Claude Code SessionStart Hook - Start escalation service and register session.

Receives via stdin:
{
  "session_id": "...",
  "hook_event_name": "SessionStart"
}
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Add parent directory to path for imports (~/bin when deployed)
sys.path.insert(0, str(Path(__file__).parent.parent))

from service import start_service, register_session


def get_claude_pid() -> int | None:
    """Walk up process tree to find Claude Code's PID."""
    pid = os.getppid()
    visited = set()

    while pid > 1 and pid not in visited:
        visited.add(pid)
        try:
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "comm=,ppid="],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                break

            parts = result.stdout.strip().split()
            if len(parts) < 2:
                break

            comm = parts[0].lower()
            ppid = int(parts[1])

            if "claude" in comm:
                return pid

            pid = ppid
        except (subprocess.CalledProcessError, ValueError):
            break

    return os.getppid()  # Fallback to direct parent


def main():
    # Read hook input from stdin (not strictly needed, but good practice)
    try:
        stdin_data = sys.stdin.read()
        hook_input = json.loads(stdin_data) if stdin_data.strip() else {}
    except json.JSONDecodeError:
        hook_input = {}

    session_id = hook_input.get("session_id", "")
    claude_pid = get_claude_pid()

    # Start the escalation service if not running
    if start_service():
        # Register this session with PID for tracking
        result = register_session(session_id=session_id, pid=claude_pid)
        if result and result.get("status") == "ok":
            count = result.get("session_count", 1)
            print(f"Session registered (pid={claude_pid}, count={count})", file=sys.stderr)
        else:
            print("Warning: Could not register session", file=sys.stderr)
    else:
        print("Warning: Could not start escalation service", file=sys.stderr)


if __name__ == "__main__":
    main()
