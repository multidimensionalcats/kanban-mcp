# Kanban MCP Server - Deployment

## Installation

1. Copy to `~/.claude/kanban-mcp/`:
   ```bash
   mkdir -p ~/.claude/kanban-mcp
   cp kanban_mcp.py kanban_cli.py ~/.claude/kanban-mcp/
   cp -r hooks ~/.claude/kanban-mcp/
   ```

2. Ensure MySQL database exists with correct schema (see schema.sql)

3. Install Python dependency:
   ```bash
   pip install mysql-connector-python
   ```

## Per-Project Configuration

For each project you want to track, create these files:

### `.mcp.json` (MCP server config)
```json
{
  "mcpServers": {
    "kanban": {
      "command": "python3",
      "args": ["${HOME}/.claude/kanban-mcp/kanban_mcp.py"],
      "env": {
        "KANBAN_PROJECT_DIR": "${CLAUDE_PROJECT_DIR}"
      }
    }
  }
}
```

### `.claude/settings.json` (Hooks config)
```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${HOME}/.claude/kanban-mcp/hooks/session_start.py"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${HOME}/.claude/kanban-mcp/hooks/stop.py"
          }
        ]
      }
    ]
  }
}
```

## How It Works

- **MCP Server**: Passes `KANBAN_PROJECT_DIR` via env var expansion
- **Hooks**: Read `CLAUDE_PROJECT_DIR` from environment (set by Claude Code)
- **Project ID**: SHA256 hash of directory path (deterministic, same for both)

## CLI Tool

For manual queries or debugging:
```bash
~/.claude/kanban-mcp/kanban_cli.py -p /path/to/project context
~/.claude/kanban-mcp/kanban_cli.py -p /path/to/project active
~/.claude/kanban-mcp/kanban_cli.py -p /path/to/project summary
```

## MCP Tools

- `set_current_project` / `get_current_project` - Project context (optional if env var set)
- `new_item` - Create issue/todo/feature/diary
- `list_items` - List with type/status filters
- `get_item` - Get item details
- `advance_status` / `revert_status` / `set_status` - Status workflow
- `close_item` / `delete_item` - Complete/remove items
- `add_update` - Add progress notes
- `get_latest_update` / `get_updates` - View updates
- `project_summary` - Counts by type/status
- `get_active_items` - In-progress items
- `get_todos` - Backlog items
