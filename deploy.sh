#!/bin/bash
# Deploy kanban-mcp to ~/kanban_mcp/
set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
DEST_DIR="$HOME/kanban_mcp"

# Python 3.13 required for onnxruntime (semantic search)
PYTHON="/usr/bin/python3.13"
if [[ ! -x "$PYTHON" ]]; then
    echo "WARNING: $PYTHON not found, falling back to python3"
    PYTHON="python3"
fi

echo "=== Deploying kanban-mcp ==="
echo "Source: $SRC_DIR"
echo "Destination: $DEST_DIR"
echo "Python: $PYTHON"

# Create destination
mkdir -p "$DEST_DIR/hooks" "$DEST_DIR/templates" "$DEST_DIR/static"

# Rsync executables and web UI
rsync -av --delete \
    --include='kanban_mcp.py' \
    --include='kanban_cli.py' \
    --include='kanban_web.py' \
    --include='kanban_export.py' \
    --include='hooks/' \
    --include='hooks/*.py' \
    --include='templates/' \
    --include='templates/*.html' \
    --include='static/' \
    --include='static/*.css' \
    --include='static/*.js' \
    --exclude='*' \
    "$SRC_DIR/" "$DEST_DIR/"

echo "Files deployed:"
ls -la "$DEST_DIR"
ls -la "$DEST_DIR/hooks"
ls -la "$DEST_DIR/templates"
ls -la "$DEST_DIR/static"

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
            jq --arg py "$PYTHON" --arg dest "$DEST_DIR" '.mcpServers.kanban = {
                "command": $py,
                "args": [($dest + "/kanban_mcp.py")]
            }' "$CLAUDE_DESKTOP_CONFIG" > "$tmp" && mv "$tmp" "$CLAUDE_DESKTOP_CONFIG"
            echo "Added kanban-mcp to Claude Desktop"
        else
            echo "WARNING: jq not installed, cannot auto-configure Claude Desktop"
            echo "Add manually to $CLAUDE_DESKTOP_CONFIG:"
            echo "  \"kanban\": { \"command\": \"$PYTHON\", \"args\": [\"$DEST_DIR/kanban_mcp.py\"] }"
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
            jq --arg py "$PYTHON" --arg dest "$DEST_DIR" '.mcpServers.kanban = {
                "command": $py,
                "args": [($dest + "/kanban_mcp.py")]
            }' "$CLAUDE_CODE_CONFIG" > "$tmp" && mv "$tmp" "$CLAUDE_CODE_CONFIG"
            echo "Added kanban-mcp to Claude Code"
        else
            echo "WARNING: jq not installed, cannot auto-configure Claude Code"
            echo "Add manually to $CLAUDE_CODE_CONFIG:"
            echo "  \"kanban\": { \"command\": \"$PYTHON\", \"args\": [\"$DEST_DIR/kanban_mcp.py\"] }"
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
            jq --arg cmd1 "$PYTHON $DEST_DIR/hooks/session_start.py" \
               --arg cmd2 "$PYTHON $DEST_DIR/hooks/stop.py" \
               '.hooks.SessionStart = (.hooks.SessionStart // []) + [{
                "type": "command",
                "command": $cmd1
            }] | .hooks.Stop = (.hooks.Stop // []) + [{
                "type": "command",
                "command": $cmd2
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
        "command": "$PYTHON $DEST_DIR/hooks/session_start.py"
      }
    ],
    "Stop": [
      {
        "type": "command",
        "command": "$PYTHON $DEST_DIR/hooks/stop.py"
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
