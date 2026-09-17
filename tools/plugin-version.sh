#!/bin/bash

# Plugin Version Control CLI for cAI-tools
# Install gum for best experience: brew install gum

set -e

BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MARKETPLACE="$BASE_DIR/.claude-plugin/marketplace.json"
MARKETPLACE_NAME="cAI-tools"
CLAUDE_PLUGINS="$HOME/.claude/plugins/installed_plugins.json"
PLUGINS=("awesome-agent" "AI-skill" "pushover" "mac" "science-skill" "stop-slop" "security")

# Check for gum
HAS_GUM=$(command -v gum &>/dev/null && echo 1 || echo 0)

# Colors & Styles
BOLD='\033[1m'
DIM='\033[2m'
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

# ─────────────────────────────────────────────────────────────
# Utility Functions
# ─────────────────────────────────────────────────────────────

header() {
    if [ "$HAS_GUM" = "1" ]; then
        gum style --border double --padding "0 2" --border-foreground 212 "$1"
    else
        echo ""
        echo -e "${MAGENTA}╔══════════════════════════════════════╗${NC}"
        echo -e "${MAGENTA}║${NC}  ${BOLD}$1${NC}"
        echo -e "${MAGENTA}╚══════════════════════════════════════╝${NC}"
        echo ""
    fi
}

success() {
    if [ "$HAS_GUM" = "1" ]; then
        gum style --foreground 10 "✓ $1"
    else
        echo -e "${GREEN}✓ $1${NC}"
    fi
}

warn() {
    if [ "$HAS_GUM" = "1" ]; then
        gum style --foreground 11 "⚠ $1"
    else
        echo -e "${YELLOW}⚠ $1${NC}"
    fi
}

error() {
    if [ "$HAS_GUM" = "1" ]; then
        gum style --foreground 9 "✗ $1"
    else
        echo -e "${RED}✗ $1${NC}"
    fi
}

info() {
    if [ "$HAS_GUM" = "1" ]; then
        gum style --foreground 12 "$1"
    else
        echo -e "${CYAN}$1${NC}"
    fi
}

# ─────────────────────────────────────────────────────────────
# Version Helpers
# ─────────────────────────────────────────────────────────────

get_marketplace_version() {
    jq -r ".plugins[] | select(.name == \"$1\") | .version" "$MARKETPLACE"
}

get_plugin_version() {
    jq -r '.version' "$BASE_DIR/plugins/$1/.claude-plugin/plugin.json"
}

get_claude_version() {
    local key="$1@$MARKETPLACE_NAME"
    if [ -f "$CLAUDE_PLUGINS" ]; then
        jq -r ".plugins[\"$key\"][0].version // \"-\"" "$CLAUDE_PLUGINS"
    else
        echo "-"
    fi
}

set_marketplace_version() {
    local tmp=$(mktemp)
    jq "(.plugins[] | select(.name == \"$1\") | .version) = \"$2\"" "$MARKETPLACE" > "$tmp"
    mv "$tmp" "$MARKETPLACE"
}

set_plugin_version() {
    local plugin_json="$BASE_DIR/plugins/$1/.claude-plugin/plugin.json"
    local tmp=$(mktemp)
    jq ".version = \"$2\"" "$plugin_json" > "$tmp"
    mv "$tmp" "$plugin_json"
}

bump_version() {
    local version="$1" type="$2"
    IFS='.' read -r major minor patch <<< "$version"
    case "$type" in
        major) echo "$((major + 1)).0.0" ;;
        minor) echo "$major.$((minor + 1)).0" ;;
        patch) echo "$major.$minor.$((patch + 1))" ;;
    esac
}

# ─────────────────────────────────────────────────────────────
# TUI Selection (gum or fallback)
# ─────────────────────────────────────────────────────────────

select_option() {
    local prompt="$1"
    shift
    local options=("$@")

    if [ "$HAS_GUM" = "1" ]; then
        gum choose --header "$prompt" "${options[@]}"
    else
        echo -e "${BOLD}$prompt${NC}"
        echo ""
        local i=1
        for opt in "${options[@]}"; do
            echo -e "  ${CYAN}$i)${NC} $opt"
            ((i++))
        done
        echo ""
        read -p "  Select [1-${#options[@]}]: " choice
        echo "${options[$((choice - 1))]}"
    fi
}

select_plugin() {
    select_option "Select a plugin:" "${PLUGINS[@]}"
}

select_bump_type() {
    select_option "Select bump type:" "patch" "minor" "major"
}

confirm() {
    if [ "$HAS_GUM" = "1" ]; then
        gum confirm "$1"
    else
        read -p "$1 [y/N]: " answer
        [[ "$answer" =~ ^[Yy] ]]
    fi
}

input_version() {
    if [ "$HAS_GUM" = "1" ]; then
        gum input --placeholder "1.0.0" --header "Enter version (semver):"
    else
        read -p "Enter version (e.g., 1.0.0): " version
        echo "$version"
    fi
}

# ─────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────

cmd_status() {
    local interactive="${1:-true}"
    header "Plugin Version Status"

    local needs_update=()

    if [ "$HAS_GUM" = "1" ]; then
        local output=""
        output+="Plugin,Manifest,Source,Installed,Status\n"
        for plugin in "${PLUGINS[@]}"; do
            mp_ver=$(get_marketplace_version "$plugin")
            pl_ver=$(get_plugin_version "$plugin")
            cl_ver=$(get_claude_version "$plugin")
            # Check sync status
            if [ "$mp_ver" == "$pl_ver" ] && [ "$pl_ver" == "$cl_ver" ]; then
                status="✓ synced"
            elif [ "$mp_ver" == "$pl_ver" ] && [ "$cl_ver" != "$pl_ver" ]; then
                status="⚠ needs update"
                needs_update+=("$plugin")
            else
                status="✗ mismatch"
            fi
            output+="$plugin,$mp_ver,$pl_ver,$cl_ver,$status\n"
        done
        echo -e "$output" | gum table
    else
        printf "  ${BOLD}%-16s %-10s %-10s %-10s %s${NC}\n" "Plugin" "Manifest" "Source" "Installed" "Status"
        printf "  ${DIM}%-16s %-10s %-10s %-10s %s${NC}\n" "────────────────" "──────────" "──────────" "──────────" "──────────────"
        for plugin in "${PLUGINS[@]}"; do
            mp_ver=$(get_marketplace_version "$plugin")
            pl_ver=$(get_plugin_version "$plugin")
            cl_ver=$(get_claude_version "$plugin")
            # Check sync status
            if [ "$mp_ver" == "$pl_ver" ] && [ "$pl_ver" == "$cl_ver" ]; then
                status="${GREEN}✓ synced${NC}"
            elif [ "$mp_ver" == "$pl_ver" ] && [ "$cl_ver" != "$pl_ver" ]; then
                status="${YELLOW}⚠ needs update${NC}"
                needs_update+=("$plugin")
            else
                status="${RED}✗ mismatch${NC}"
            fi
            printf "  %-16s %-10s %-10s %-10s " "$plugin" "$mp_ver" "$pl_ver" "$cl_ver"
            echo -e "$status"
        done
    fi
    echo ""
    echo -e "  ${DIM}Manifest = marketplace.json | Source = plugin.json | Installed = Claude CLI${NC}"
    echo ""

    # Offer to update if there are plugins needing update and in interactive mode
    if [ "$interactive" = "true" ] && [ ${#needs_update[@]} -gt 0 ]; then
        echo ""
        warn "${#needs_update[@]} plugin(s) need updating: ${needs_update[*]}"
        echo ""

        local options=("Update all" "Cancel")
        for p in "${needs_update[@]}"; do
            options=("${options[@]:0:1}" "Update $p" "${options[@]:1}")
        done

        local action=$(select_option "Would you like to update?" "${options[@]}")

        case "$action" in
            "Update all")
                echo ""
                for p in "${needs_update[@]}"; do
                    info "Updating $p..."
                    claude plugin update "$p@$MARKETPLACE_NAME"
                done
                echo ""
                success "All updates complete. Restart Claude Code to apply."
                ;;
            "Cancel")
                ;;
            Update*)
                local p="${action#Update }"
                echo ""
                info "Updating $p..."
                claude plugin update "$p@$MARKETPLACE_NAME"
                echo ""
                success "Update complete. Restart Claude Code to apply."
                ;;
        esac
    fi
}

cmd_bump() {
    local plugin="$1" type="$2"

    [ -z "$plugin" ] && plugin=$(select_plugin)
    [ -z "$type" ] && type=$(select_bump_type)

    local current=$(get_plugin_version "$plugin")
    local new=$(bump_version "$current" "$type")

    echo ""
    info "Bumping $plugin: $current → $new"

    set_plugin_version "$plugin" "$new"
    set_marketplace_version "$plugin" "$new"

    success "Updated plugin.json and marketplace.json"
}

cmd_bump_all() {
    local type="$1"

    [ -z "$type" ] && type=$(select_bump_type)

    header "Bump All Plugins ($type)"

    for plugin in "${PLUGINS[@]}"; do
        local current=$(get_plugin_version "$plugin")
        local new=$(bump_version "$current" "$type")
        info "  $plugin: $current → $new"
        set_plugin_version "$plugin" "$new"
        set_marketplace_version "$plugin" "$new"
    done

    echo ""
    success "All plugins updated"
}

cmd_set() {
    local plugin="$1" version="$2"

    [ -z "$plugin" ] && plugin=$(select_plugin)
    [ -z "$version" ] && version=$(input_version)

    if ! [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        error "Invalid version format. Use semver (e.g., 1.2.3)"
        exit 1
    fi

    local current=$(get_plugin_version "$plugin")

    echo ""
    info "Setting $plugin: $current → $version"

    set_plugin_version "$plugin" "$version"
    set_marketplace_version "$plugin" "$version"

    success "Updated plugin.json and marketplace.json"
}

cmd_sync() {
    header "Sync Versions"

    local synced=0

    for plugin in "${PLUGINS[@]}"; do
        local mp_ver=$(get_marketplace_version "$plugin")
        local pl_ver=$(get_plugin_version "$plugin")

        if [ "$mp_ver" != "$pl_ver" ]; then
            info "  $plugin: marketplace $mp_ver → $pl_ver"
            set_marketplace_version "$plugin" "$pl_ver"
            synced=$((synced + 1))
        fi
    done

    if [ $synced -eq 0 ]; then
        success "All versions already in sync"
    else
        echo ""
        success "Synced $synced plugin(s)"
    fi
}

cmd_interactive() {
    while true; do
        header "Plugin Version Control"

        local action=$(select_option "What would you like to do?" \
            "📊 Status - View versions & update" \
            "🔄 Update - Update Claude plugins" \
            "⬆️  Bump - Increment a plugin version" \
            "⬆️  Bump All - Increment all plugins" \
            "✏️  Set - Set specific version" \
            "📋 Sync - Sync to marketplace.json" \
            "🚪 Exit")

        echo ""

        case "$action" in
            "📊 Status"*) cmd_status ;;
            "🔄 Update"*) cmd_update ;;
            "⬆️  Bump -"*) cmd_bump ;;
            "⬆️  Bump All"*) cmd_bump_all ;;
            "✏️  Set"*) cmd_set ;;
            "📋 Sync"*) cmd_sync ;;
            "🚪 Exit"*) echo "Bye!"; exit 0 ;;
        esac

        echo ""
        if [ "$HAS_GUM" != "1" ]; then
            read -p "Press Enter to continue..."
        else
            gum spin --spinner dot --title "Returning to menu..." -- sleep 0.5
        fi
        clear
    done
}

# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

cmd_update() {
    local plugin="$1"

    if [ -z "$plugin" ]; then
        # Interactive: let user choose
        local options=("All plugins" "${PLUGINS[@]}")
        plugin=$(select_option "Select plugin to update:" "${options[@]}")
    fi

    if [ "$plugin" = "All plugins" ]; then
        header "Update All Plugins"
        for p in "${PLUGINS[@]}"; do
            info "Updating $p..."
            claude plugin update "$p@$MARKETPLACE_NAME"
        done
        echo ""
        success "All plugins updated. Restart Claude Code to apply."
    else
        # Update single plugin
        if [[ ! " ${PLUGINS[*]} " =~ " $plugin " ]]; then
            error "Unknown plugin '$plugin'"
            echo "Available plugins: ${PLUGINS[*]}"
            exit 1
        fi
        info "Updating $plugin..."
        claude plugin update "$plugin@$MARKETPLACE_NAME"
        echo ""
        success "Update complete. Restart Claude Code to apply."
    fi
}

usage() {
    echo "Plugin Version Control CLI"
    echo ""
    echo "Usage: $0 [command] [args]"
    echo ""
    echo "Commands:"
    echo "  (none)              Interactive TUI mode"
    echo "  status              Show version status (+ update prompt)"
    echo "  update [plugin]     Update plugin(s) in Claude CLI"
    echo "  bump [plugin] [type]  Bump version (patch|minor|major)"
    echo "  bump-all [type]     Bump all plugins"
    echo "  set [plugin] [ver]  Set specific version"
    echo "  sync                Sync to marketplace.json"
    echo ""
    if [ "$HAS_GUM" != "1" ]; then
        echo -e "${DIM}Tip: Install gum for better TUI: brew install gum${NC}"
    fi
}

case "${1:-}" in
    "")
        cmd_interactive
        ;;
    status)
        cmd_status
        ;;
    update)
        cmd_update "$2"
        ;;
    bump)
        cmd_bump "$2" "$3"
        ;;
    bump-all)
        cmd_bump_all "$2"
        ;;
    set)
        cmd_set "$2" "$3"
        ;;
    sync)
        cmd_sync
        ;;
    -h|--help|help)
        usage
        ;;
    *)
        usage
        exit 1
        ;;
esac
