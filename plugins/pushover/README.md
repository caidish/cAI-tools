# Pushover Plugin for Claude Code

Push notifications for Claude Code via Pushover.

## Features

- **Permission Escalation**: Get notified when Claude is waiting for permission approval
- **Task Completion**: Low-priority notification when Claude finishes a task
- **Session Management**: Automatic service lifecycle tied to Claude sessions
- **On-Demand Notifications**: Send push notifications via the `notification` skill

## Notification Skill

Send push notifications on demand:

```bash
# Basic notification
"Send me a notification when you're done"

# With priority
"Notify me urgently if the build fails"
```

Priority levels: -2 (silent), -1 (quiet), 0 (normal), 1 (high), 2 (emergency)

## Escalation System

When Claude requests permission and waits for user approval, the escalation system sends increasingly urgent notifications:

| Delay | Priority | Description |
|-------|----------|-------------|
| 60s | Normal (0) | First reminder |
| 1 hour | Emergency (2) | Requires acknowledgment |

### Architecture

```
┌─────────────────┐     ┌──────────────────────┐
│  Claude Code    │────▶│  Escalation Service  │
│  Hooks          │     │  (Unix socket)       │
└─────────────────┘     └──────────────────────┘
        │                         │
        │                         ▼
        │               ┌──────────────────────┐
        └──────────────▶│  Pushover API        │
                        │  (po_notify.py)      │
                        └──────────────────────┘
```

### Hook Flow

1. **SessionStart** → Starts escalation service, registers session
2. **Notification (permission_prompt)** → Adds escalation timer
3. **User activity** → Cancels escalation timer
4. **SessionEnd** → Unregisters session, may stop service

### Session-Level Tracking

The escalation system uses **session-level tracking** (not per-tool tracking). This means:

- Only one escalation timer per session at a time
- Any subsequent activity cancels the pending escalation

**Hooks that cancel escalations:**
- `PreToolUse` - Claude is about to use another tool
- `PermissionRequest` - Another permission dialog appears
- `PostToolUse` - A tool finished executing
- `PostToolUseFailure` - A tool execution failed
- `UserPromptSubmit` - User submitted a new prompt
- `Stop` - Claude finished responding
- `PreCompact` - Session is being compacted

### Known Limitations

1. **No hook for permission acceptance/rejection**: Claude Code does not have a hook that fires when a user accepts or rejects a permission prompt. The system relies on downstream hooks (`PreToolUse` after acceptance, `Stop` after rejection) to cancel escalations. This creates gaps in scenarios like plan mode context clearing and long tool call submissions, where these downstream hooks may fire late or not at all.

2. **Race condition on rapid tool use**: If Claude uses multiple tools rapidly, escalations may be added and cancelled quickly. This is by design - session-level tracking prioritizes simplicity over precision.

3. **Service persistence**: The escalation service runs as a separate process and uses reference counting. If Claude Code crashes without firing `SessionEnd`, the service may persist until manually stopped.

## Files

```
pushover/
├── hooks/hooks.json           # Hook configuration
├── scripts/
│   ├── hooks/
│   │   ├── on_session_start.py    # Start service, register session
│   │   ├── on_session_end.py      # Unregister session
│   │   ├── on_permission.py       # Add escalation on permission prompt
│   │   ├── on_stop.py             # Send completion notification, cancel escalation
│   │   └── cancel_escalation.py   # Cancel escalation (shared by multiple hooks)
│   └── service/
│       ├── escalation_service.py  # Background escalation manager
│       ├── escalation_client.py   # Client library for service communication
│       └── escalation_ctl.py      # CLI for manual control
├── skills/
│   └── notification/
│       ├── SKILL.md               # Skill definition
│       └── scripts/notify.sh      # Notification script
└── tools/
    └── pushover-notify/
        └── po_notify.py           # Pushover API wrapper
```

## Manual Control

Use `escalation_ctl.py` to manage the service:

```bash
# Check status
python3 scripts/service/escalation_ctl.py status

# Add test escalation
python3 scripts/service/escalation_ctl.py add test-id "Test message"

# Cancel escalation
python3 scripts/service/escalation_ctl.py cancel test-id

# Stop service
python3 scripts/service/escalation_ctl.py stop
```

## Setup

Run the setup script from the repository root:

```bash
./setup-service.sh
```

This will prompt for your Pushover credentials and store them securely in macOS Keychain:
- `pushover_app_token` - Your Pushover API token
- `pushover_iphone_key` - Your Pushover user key

Get these from https://pushover.net/
