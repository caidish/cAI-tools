#!/usr/bin/env python3
"""
Claude Code Stop Hook - Task Completion Notification

Sends a low-priority Pushover notification when Claude finishes a task.
Extracts a summary from the conversation transcript.

Receives via stdin:
{
  "session_id": "...",
  "transcript_path": "~/.claude/projects/.../conversation.jsonl",
  "hook_event_name": "Stop",
  "stop_hook_active": false
}
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def get_last_assistant_text(transcript_path: str, max_words: int = 100) -> str:
    """Extract the last assistant text message from the transcript."""
    path = Path(transcript_path).expanduser()
    if not path.exists():
        return "Task completed"

    last_text = ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    msg = entry.get("message", {})
                    if msg.get("role") == "assistant":
                        content = msg.get("content", [])
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                last_text = block.get("text", "")
                except json.JSONDecodeError:
                    continue
    except Exception:
        return "Task completed"

    if not last_text:
        return "Task completed"

    # Truncate to max_words
    words = last_text.split()
    if len(words) > max_words:
        return " ".join(words[:max_words]) + "..."
    return last_text


def send_notification(title: str, message: str, priority: int = -1) -> None:
    """Send notification via po_notify."""
    po_notify = Path("~/bin/po_notify").expanduser()
    if not po_notify.exists():
        # Try system PATH
        po_notify = "po_notify"

    try:
        # po_notify uses: title message --priority N
        subprocess.run(
            [str(po_notify), title, message, "--priority", str(priority)],
            check=True,
            capture_output=True,
            timeout=10,
        )
    except subprocess.CalledProcessError as e:
        print(f"Notification failed: {e.stderr.decode()}", file=sys.stderr)
    except FileNotFoundError:
        print("po_notify not found. Install pushover-notify first.", file=sys.stderr)
    except Exception as e:
        print(f"Notification error: {e}", file=sys.stderr)


def main():
    # Skip notification if ralph-loop is active (avoid noisy notifications during iterations)
    if Path(".claude/ralph-loop.local.md").exists():
        return

    # Read hook input from stdin
    try:
        stdin_data = sys.stdin.read()
        hook_input = json.loads(stdin_data) if stdin_data.strip() else {}
    except json.JSONDecodeError:
        hook_input = {}

    transcript_path = hook_input.get("transcript_path", "")

    # Extract summary from transcript
    if transcript_path:
        summary = get_last_assistant_text(transcript_path)
    else:
        summary = "Task completed"

    # Send low-priority notification
    send_notification("Claude Done", summary, priority=-1)


if __name__ == "__main__":
    main()
