# Kanban MCP Server

A centralized issue/todo/feature/diary tracking system for Claude Code projects, backed by MySQL.

## Features

- **Unified tracking**: Issues, todos, features, and diary entries in one place
- **Project-based**: Items are scoped to projects (identified by directory path hash)
- **Status workflows**: Different item types have different valid status progressions
- **Updates/Progress logs**: Log progress that can reference multiple items
- **MCP integration**: Works with Claude Code via STDIO JSON-RPC

## Item Types & Workflows

| Type | Workflow |
|------|----------|
| issue | backlog → todo → in_progress → review → done → closed |
| feature | backlog → todo → in_progress → review → done → closed |
| todo | backlog → todo → in_progress → done |
| diary | done (single state) |

## Tools

| Tool | Description |
|------|-------------|
| `new_item` | Create issue/todo/feature/diary |
| `list_items` | Query items with filters |
| `get_item` | Get full item details |
| `advance_status` | Move to next workflow state |
| `revert_status` | Move to previous state |
| `set_status` | Jump to specific status |
| `close_item` | Mark done + set closed_at |
| `delete_item` | Permanently delete |
| `add_update` | Log progress (can reference multiple items) |
| `get_latest_update` | Most recent update for project |
| `get_updates` | Recent updates for project |
| `project_summary` | Dashboard: counts by type/status |
| `get_active_items` | Items in 'in_progress' status |

## Setup

### Database

```sql
-- Create database and user (as root)
CREATE DATABASE claude_code_kanban;
CREATE USER 'claude'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON claude_code_kanban.* TO 'claude'@'localhost';
FLUSH PRIVILEGES;
```

Then run the schema (see schema.sql or the CREATE TABLE statements in the project docs).

### Python

```bash
pip install -r requirements.txt
```

### Claude Desktop Config

Add to `~/.config/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "kanban": {
      "command": "python3",
      "args": ["/path/to/kanban-mcp/kanban_mcp.py"]
    }
  }
}
```

## Usage with Claude Code Hooks

Example `.claude/hooks.toml`:

```toml
[[hooks]]
event = "PreToolUse"
matcher = { tool_name = { any_of = ["bash", "write", "edit"] } }
command = "python3 /path/to/kanban-mcp/hook_get_active.py"

[[hooks]]
event = "Stop"
command = "python3 /path/to/kanban-mcp/hook_diary_prompt.py"
```

## License

MIT
