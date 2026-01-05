# cAI-tools
A collection of Claude Code plugins containing custom agents, skills, commands, and notification hooks.

Tested with macOS Claude Code v2.0.76+.

The plugin is made conservative in context usage by keeping concise and precise writing.

## Plugins

| Plugin | Description |
|--------|-------------|
| **awesome-agent** | Collection of useful prompted subagents for code review, API docs, QA, and more. Variant from: [awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents) |
| **AI-skill** | Skills for interacting with other AI tools - Codex, Gemini CLI, and collaboration fixes. Codex is a variant from [Skill Codex](https://github.com/skills-directory/skill-codex)|
| **pushover** | Pushover notification hooks - get notified when tasks complete or permissions are needed |
| **mac** | macOS integration - speak, send iMessages, emails, manage calendar, and display stickies |

## Example:
1. AI-skill: `Use codex and gemini-cli to review uncommitted changes.` `Check this with codex` `AI-skill:collob-fix Fix the bug showing here as ### Bug 3`
2. mac: `after you finish, use mac to say "All done" and a brief summary of what you did.` ``Use imessage to send me (my email address/phone number) a message "Task complete" with the summary.` `Can you add this to my stikies?` `Use mac to generate today's calendar schedule with the information on my stikies.`. 

<img width="330" height="326" alt="macTools" src="https://github.com/user-attachments/assets/674ac8d8-d62a-4e5a-bd6c-584991634c36" />
<img width="206" height="46" alt="Pushover" src="https://github.com/user-attachments/assets/e3965610-31f8-4aec-a36c-c94c2cf0aef2" />
<img width="202" height="117" alt="Sticker" src="https://github.com/user-attachments/assets/d76ca525-757a-4768-835d-803cb5c7eca6" />

## Known Issues:
1. Pushover: Claude Code does not have a hook that fires specifically when a user rejects a permission prompt. The system relies on subsequent activity (like `Stop` or `UserPromptSubmit`) to cancel escalations. I believe this is a limitation of Claude Code's current hook system, and should be addressed in future versions. We now use a simple session-level tracking to manage escalations (a daemon that send notification by timing). The Pushover is now very annoying because of the 60s, but it is a good push for me. You can change it here [escalation service](plugins/pushover/scripts/service/escalation_service.py)
2. mac: The `ical.sh` script reads all calendars but only writes to a calendar named "Agent". If your calendar contains sensitive information, be cautious when using this skill.
3. All email/message/calendar features depend on the respective macOS apps being properly configured with accounts. First run of osascript may prompt for permissions. 

## Installation

### Add the Marketplace

```bash
claude plugin marketplace add /path/to/cAI-tools
```

### Install Plugins

You can enter claude interface and use /plugin to navigate to my marketplace and install each plugin. 

```bash
# Install all plugins
claude plugin install awesome-agent@cAI-tools
claude plugin install AI-skill@cAI-tools
claude plugin install pushover@cAI-tools
claude plugin install mac@cAI-tools
```

### Pushover Setup (for pushover plugin)

Run the one-time setup to store your Pushover credentials in macOS Keychain:

```bash
./setup-service.sh
```

Get your credentials from [pushover.net](https://pushover.net/).

## Plugin Details

### awesome-agent

Specialized task agents for various workflows:

- `api-documenter` - API documentation generation
- `code-reviewer` - Code review and suggestions
- `llm-architect` - LLM system design
- `mcp-developer` - MCP server development
- `performance-engineer` - Performance optimization
- `qa-expert` - Quality assurance
- `qcodes-specialist` - QCodes instrumentation
- `quantum-device-specialist` - Quantum device control
- `test-automator` - Test automation
- `tooling-engineer` - Developer tooling
- `typescript-pro` - TypeScript expertise

### AI-skill

Skills for AI tool integration:

| Skill | Description |
|-------|-------------|
| codex | OpenAI Codex CLI integration |
| gemini-cli | Google Gemini CLI integration |

Command: `/AI-skill:collab-fix` - Collaborative multi-agent fix workflow

### pushover

Push notifications via Pushover with automatic escalation system.

**Skill:** `notification` - Send on-demand push notifications to your phone

**Hooks:** Automatic permission escalation - get notified when Claude is waiting for approval (60s normal, 1hr emergency)

See [pushover/README.md](plugins/pushover/README.md) for architecture details and configuration.

### mac

macOS native app integration:

| Feature | Command | Description |
|---------|---------|-------------|
| Text-to-Speech | `say` | Speak messages aloud |
| iMessage | `imessage.sh` | Send iMessages |
| Email | `imail.sh` | Send emails via Mail.app |
| Calendar | `ical.sh` | List/add events (reads all, writes to "Agent" calendar) |
| Stickies | `iStickies.sh` | Read and write notes with markdown support |

## Uninstallation

```bash
claude plugin uninstall awesome-agent@cAI-tools
claude plugin uninstall AI-skill@cAI-tools
claude plugin uninstall pushover@cAI-tools
claude plugin uninstall mac@cAI-tools
```

## Bash Timeout Settings
For best experience with long-running tasks:

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

## Version Control

A TUI tool for managing plugin versions across `marketplace.json`, `plugin.json`, and Claude CLI.

### Setup for human

Install [gum](https://github.com/charmbracelet/gum) for the best TUI experience (optional):

```bash
brew install gum
```

Interactive TUI mode:
```bash
./tools/plugin-version.sh
```

### AI Usage
Examples:
```bash
# CLI commands
./tools/plugin-version.sh status              # View version status
./tools/plugin-version.sh update              # Update plugins in Claude
./tools/plugin-version.sh update mac          # Update specific plugin
./tools/plugin-version.sh bump mac patch      # Bump version (patch/minor/major)
./tools/plugin-version.sh bump-all minor      # Bump all plugins
./tools/plugin-version.sh set mac 2.0.0       # Set specific version
./tools/plugin-version.sh sync                # Sync plugin.json to marketplace.json
```

### AI Workflow

If changes are makde to a plugin
1. Run `./tools/plugin-version.sh bump <plugin> patch` to increment version
2. Run `./tools/plugin-version.sh status` to see status and update Claude
