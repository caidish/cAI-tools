# My Agent Prompts
The following has been tested to work with MacOS Claude Code (v2.0.76+).

The repo contains some of my favorite agent prompts, skills, commands, and hooks for Claude Code.

Agents: lightly modified versions of those shared by Anthropic, as well as some custom ones.

Skills: modifed version from https://github.com/skills-directory/skill-codex, and gemini-cli skills. 

Commands: custom slash commands for colloborations of claude subagent, codex and gemini-cli. 

Hooks: pushover integration for push notifications.

## Agents and Skills

- `agents/` - Agent profiles for specialized tasks (code review, API documentation, etc.)
- `skills/` - Reusable skill definitions for Claude Code
- `commands/` - Slash commands for Claude Code
- `hooks-tool/` - Push notification hooks for Claude Code
- `tools/pushover-notify/` - Pushover notification script

## Setup

### Auto Install

```bash
./install.sh
```

This will:
- Symlink `agents/`, `skills/`, `commands/` to `~/.claude/`
- Copy notification hooks to `~/bin/`
- Prompt for Pushover credentials

Then update `~/.claude/settings.json` with hooks config (see [hooks-tool/settings.json](hooks-tool/settings.json)) and restart Claude Code.

### Auto Uninstall

```bash
./uninstall.sh
```

This will remove symlinks, hooks, and optionally Keychain credentials.

### Manual Install

Symlink agents, skills, and commands:

```bash
ln -s /path/to/this/repo/agents ~/.claude/agents
ln -s /path/to/this/repo/skills ~/.claude/skills
ln -s /path/to/this/repo/commands ~/.claude/commands
```

Or copy them:

```bash
mkdir -p ~/.claude/agents ~/.claude/skills ~/.claude/commands
cp -r /path/to/this/repo/agents/* ~/.claude/agents/
cp -r /path/to/this/repo/skills/* ~/.claude/skills/
cp -r /path/to/this/repo/commands/* ~/.claude/commands/
```

For notification hooks, see [hooks-tool/README.md](hooks-tool/README.md).

## Bash Timeout Settings

Add to `~/.claude/settings.json` to extend bash timeouts:

```json
{
  "env": {
    "BASH_DEFAULT_TIMEOUT_MS": "600000",
    "BASH_MAX_TIMEOUT_MS": "3600000"
  }
}
```

| Setting | Value | Description |
|---------|-------|-------------|
| `BASH_DEFAULT_TIMEOUT_MS` | 600000 | Default timeout: 10 min |
| `BASH_MAX_TIMEOUT_MS` | 3600000 | Max timeout: 1 hour |
