#!/bin/bash
# Uninstall Claude Code agents, skills, commands, and notification hooks

echo "Uninstalling Claude Code components..."

# Remove symlinks
rm -f ~/.claude/agents
rm -f ~/.claude/skills
rm -f ~/.claude/commands
echo "Removed symlinks from ~/.claude/"

# Remove hook scripts
rm -f ~/bin/hooks/on_session_start.py
rm -f ~/bin/hooks/on_session_end.py
rm -f ~/bin/hooks/on_permission.py
rm -f ~/bin/hooks/on_post_tool.py
rm -f ~/bin/hooks/on_stop.py
rmdir ~/bin/hooks 2>/dev/null || true

# Remove service files
rm -f ~/bin/service/escalation_service.py
rm -f ~/bin/service/escalation_client.py
rm -f ~/bin/service/escalation_ctl.py
rm -f ~/bin/service/__init__.py
rmdir ~/bin/service 2>/dev/null || true

# Remove pushover-notify
rm -f ~/bin/po_notify

# Remove socket and lock files
rm -f ~/bin/run/escalation.sock
rm -f ~/bin/run/escalation.lock
rmdir ~/bin/run 2>/dev/null || true
# Also clean up old locations
rm -f ~/.claude/escalation.sock
rm -f ~/.claude/escalation.lock
rm -f /tmp/claude-escalation.sock
rm -f /tmp/claude-escalation.lock

echo "Files removed from ~/bin/"
echo ""

# Ask about keychain credentials
read -p "Remove Pushover credentials from Keychain? [y/N] " remove_creds
if [[ "$remove_creds" =~ ^[Yy]$ ]]; then
    security delete-generic-password -s pushover_app_token 2>/dev/null || true
    security delete-generic-password -s pushover_iphone_key 2>/dev/null || true
    echo "Credentials removed."
fi

echo ""
echo "Done! Next step:"
echo "  Ask Claude Code to update its default setting to exclude hooks-tool/settings.json."
echo ""
echo "Then restart Claude Code."
