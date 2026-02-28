#!/usr/bin/env python3
"""
Cancel Escalation Hook - Cancels pending escalation when user activity detected.

This script is triggered by multiple hooks to ensure escalations are cancelled
when the user responds to permission prompts (accept OR reject) or any other
activity that indicates the user is present.

Triggered by: PreToolUse, PermissionRequest, PostToolUse, PostToolUseFailure,
              UserPromptSubmit, Stop, PreCompact

Uses session-level tracking (not tool_use_id) to handle all response types.

Receives via stdin:
{
  "session_id": "...",
  "hook_event_name": "...",
  ...
}
"""

import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from service import cancel_escalation, get_client


def main():
    # Read hook input from stdin
    try:
        stdin_data = sys.stdin.read()
        hook_input = json.loads(stdin_data) if stdin_data.strip() else {}
    except json.JSONDecodeError:
        hook_input = {}

    session_id = hook_input.get("session_id", "")
    hook_event = hook_input.get("hook_event_name", "")

    if not session_id:
        return

    client = get_client()
    if not client.is_running():
        return

    # Cancel escalation using session_id as the key
    result = cancel_escalation(session_id)
    cancelled = result and result.get("cancelled")

    if cancelled:
        print(f"Cancelled escalation for session (triggered by {hook_event})", file=sys.stderr)


if __name__ == "__main__":
    main()
