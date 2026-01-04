#!/bin/bash
# Install Claude Code agents, skills, commands, and notification hooks

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOKS_DIR="$SCRIPT_DIR/hooks-tool"
PUSHOVER_DIR="$SCRIPT_DIR/tools/pushover-notify"

echo "Installing Claude Code components..."

# Create directories
mkdir -p ~/bin/hooks ~/bin/service ~/bin/run ~/.claude/logs

# Symlink agents, skills, and commands
echo "Creating symlinks to ~/.claude/..."
ln -sfn "$SCRIPT_DIR/agents" ~/.claude/agents
ln -sfn "$SCRIPT_DIR/skills" ~/.claude/skills
ln -sfn "$SCRIPT_DIR/commands" ~/.claude/commands
echo "  ~/.claude/agents -> $SCRIPT_DIR/agents"
echo "  ~/.claude/skills -> $SCRIPT_DIR/skills"
echo "  ~/.claude/commands -> $SCRIPT_DIR/commands"
echo ""

# Copy pushover-notify
cp "$PUSHOVER_DIR/po_notify.py" ~/bin/po_notify
chmod +x ~/bin/po_notify

# Copy hook scripts
cp "$HOOKS_DIR/hooks/"*.py ~/bin/hooks/
chmod +x ~/bin/hooks/*.py

# Copy service files
cp "$HOOKS_DIR/service/"*.py ~/bin/service/
chmod +x ~/bin/service/*.py

echo "Files installed to ~/bin/, ~/bin/hooks/, ~/bin/service/"
echo ""

# Configure Pushover credentials
echo "Configuring Pushover credentials..."
echo "(Get these from https://pushover.net/)"
echo ""

read -p "Pushover API Token: " api_token
read -p "Pushover User Key: " user_key

if [ -n "$api_token" ] && [ -n "$user_key" ]; then
    security add-generic-password -U -a "$USER" -s pushover_app_token -w "$api_token"
    security add-generic-password -U -a "$USER" -s pushover_iphone_key -w "$user_key"
    echo "Credentials saved to Keychain."
else
    echo "Skipped credential setup. Configure manually later:"
    echo "  security add-generic-password -U -a \"\$USER\" -s pushover_app_token -w \"YOUR_API_TOKEN\""
    echo "  security add-generic-password -U -a \"\$USER\" -s pushover_iphone_key -w \"YOUR_USER_KEY\""
fi

echo ""
echo "Done! Next step:"
echo "  Ask Claude Code to update its default setting to include hooks-tool/settings.json."
echo ""
echo "Then restart Claude Code."
