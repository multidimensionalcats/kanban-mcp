#!/bin/bash
# Deploy kanban-mcp to ~/kanban_mcp/
set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
DEST_DIR="$HOME/kanban_mcp"

echo "=== Deploying kanban-mcp ==="
echo "Source: $SRC_DIR"
echo "Destination: $DEST_DIR"

# Create destination
mkdir -p "$DEST_DIR/hooks"

# Rsync executables only
rsync -av --delete \
    --include='kanban_mcp.py' \
    --include='kanban_cli.py' \
    --include='hooks/' \
    --include='hooks/*.py' \
    --exclude='*' \
    "$SRC_DIR/" "$DEST_DIR/"

echo "Files deployed:"
ls -la "$DEST_DIR"
ls -la "$DEST_DIR/hooks"

# --- Claude Desktop config ---
CLAUDE_DESKTOP_CONFIG="$HOME/.config/Claude/claude_desktop_config.json"
if [[ -f "$CLAUDE_DESKTOP_CONFIG" ]]; then
    echo ""
    echo "=== Claude Desktop config found ==="
    if grep -q '"kanban"' "$CLAUDE_DESKTOP_CONFIG" 2>/dev/null; then
        echo "kanban-mcp already configured in Claude Desktop"
    else
        echo "Adding kanban-mcp to Claude Desktop config..."
        if command -v jq &>/dev/null; then
            tmp=$(mktemp)
            jq '.mcpServers.kanban = {
                "command": "python3",
                "args": ["'"$DEST_DIR"'/kanban_mcp.py"]
            }' "$CLAUDE_DESKTOP_CONFIG" > "$tmp" && mv "$tmp" "$CLAUDE_DESKTOP_CONFIG"
            echo "Added kanban-mcp to Claude Desktop"
        else
            echo "WARNING: jq not installed, cannot auto-configure Claude Desktop"
            echo "Add manually to $CLAUDE_DESKTOP_CONFIG:"
            echo '  "kanban": { "command": "python3", "args": ["'"$DEST_DIR"'/kanban_mcp.py"] }'
        fi
    fi
else
    echo ""
    echo "Claude Desktop config not found at $CLAUDE_DESKTOP_CONFIG (skipping)"
fi

# --- Claude Code central config ---
CLAUDE_CODE_CONFIG="$HOME/.claude.json"
if [[ -f "$CLAUDE_CODE_CONFIG" ]]; then
    echo ""
    echo "=== Claude Code config found ==="
    if grep -q '"kanban"' "$CLAUDE_CODE_CONFIG" 2>/dev/null; then
        echo "kanban-mcp already configured in Claude Code"
    else
        echo "Adding kanban-mcp to Claude Code config..."
        if command -v jq &>/dev/null; then
            tmp=$(mktemp)
            jq '.mcpServers.kanban = {
                "command": "python3",
                "args": ["'"$DEST_DIR"'/kanban_mcp.py"]
            }' "$CLAUDE_CODE_CONFIG" > "$tmp" && mv "$tmp" "$CLAUDE_CODE_CONFIG"
            echo "Added kanban-mcp to Claude Code"
        else
            echo "WARNING: jq not installed, cannot auto-configure Claude Code"
            echo "Add manually to $CLAUDE_CODE_CONFIG:"
            echo '  "kanban": { "command": "python3", "args": ["'"$DEST_DIR"'/kanban_mcp.py"] }'
        fi
    fi
else
    echo ""
    echo "Claude Code config not found at $CLAUDE_CODE_CONFIG (skipping)"
fi

# --- Claude Code hooks (central) ---
CLAUDE_CODE_SETTINGS="$HOME/.claude/settings.json"
echo ""
echo "=== Claude Code hooks ==="
mkdir -p "$HOME/.claude"

if [[ -f "$CLAUDE_CODE_SETTINGS" ]]; then
    if grep -q 'kanban_mcp' "$CLAUDE_CODE_SETTINGS" 2>/dev/null; then
        echo "Hooks already configured in $CLAUDE_CODE_SETTINGS"
    else
        echo "Adding hooks to Claude Code settings..."
        if command -v jq &>/dev/null; then
            tmp=$(mktemp)
            jq '.hooks.SessionStart = (.hooks.SessionStart // []) + [{
                "type": "command",
                "command": "python3 '"$DEST_DIR"'/hooks/session_start.py"
            }] | .hooks.Stop = (.hooks.Stop // []) + [{
                "type": "command",
                "command": "python3 '"$DEST_DIR"'/hooks/stop.py"
            }]' "$CLAUDE_CODE_SETTINGS" > "$tmp" && mv "$tmp" "$CLAUDE_CODE_SETTINGS"
            echo "Added hooks to Claude Code settings"
        else
            echo "WARNING: jq not installed, cannot auto-configure hooks"
        fi
    fi
else
    echo "Creating $CLAUDE_CODE_SETTINGS with hooks..."
    cat > "$CLAUDE_CODE_SETTINGS" << EOF
{
  "hooks": {
    "SessionStart": [
      {
        "type": "command",
        "command": "python3 $DEST_DIR/hooks/session_start.py"
      }
    ],
    "Stop": [
      {
        "type": "command",
        "command": "python3 $DEST_DIR/hooks/stop.py"
      }
    ]
  }
}
EOF
    echo "Created $CLAUDE_CODE_SETTINGS"
fi

echo ""
echo "=== Deployment complete ==="
echo ""
echo "Note: Claude Desktop doesn't support hooks."
echo "Note: For per-project env var config, add .mcp.json to project with:"
echo '  "env": { "KANBAN_PROJECT_DIR": "${CLAUDE_PROJECT_DIR}" }'
