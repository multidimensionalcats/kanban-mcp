# kanban-mcp

A database-backed kanban board that AI coding agents use via [MCP](https://modelcontextprotocol.io/) (Model Context Protocol). Track issues, features, todos, epics, and diary entries across all your projects — with a web UI for humans and 40+ tools for agents.

## What It Does

- **Persistent project tracking** — issues, features, todos, epics, diary entries stored in MySQL
- **Status workflows** — each item type has its own progression (backlog → todo → in_progress → review → done → closed)
- **Relationships & epics** — parent/child hierarchies, blocking relationships, epic progress tracking
- **Tags, decisions, file links** — attach metadata to any item
- **Semantic search** — find similar items using local ONNX embeddings (optional)
- **Activity timeline** — unified view of status changes, decisions, updates, and git commits
- **Export** — JSON, YAML, or Markdown output with filters
- **Web UI** — browser-based board at localhost:5000
- **Session hooks** — inject active items into Claude Code sessions automatically

## Quick Start

```bash
pip install kanban-mcp

# Set up MySQL database (interactive)
kanban-setup

# Add to your MCP client (see Configuration below)
```

## Installation

### Option 1: pip (recommended)

```bash
pip install kanban-mcp
```

For semantic search (local embeddings, ~100MB model download on first use):

```bash
pip install kanban-mcp[semantic]
```

### Option 2: Docker

```bash
git clone https://github.com/multidimensionalcats/kanban-mcp.git
cd kanban-mcp
docker compose up
```

This starts MySQL 8.0 and the web UI on port 5000. Migrations run automatically. The MCP server still needs to be configured separately in your AI client (see Configuration).

### Option 3: From source

```bash
git clone https://github.com/multidimensionalcats/kanban-mcp.git
cd kanban-mcp
python3 -m venv .venv && source .venv/bin/activate  # recommended
pip install -e .          # or pip install -e .[semantic] for semantic search
pip install -e .[dev]     # for development (pytest)
```

Then set up the database manually (see below) or run `kanban-setup`.

## Database Setup

Requires **MySQL 8.0+** running locally (or remotely).

### Automated (interactive)

```bash
kanban-setup
```

Prompts for database name, user, and password, then creates the database, runs migrations, and generates a `.env` file.

To also install semantic search dependencies:

```bash
kanban-setup --with-semantic
```

### Automated (non-interactive / AI agents)

For automation or when an AI agent is installing on your behalf:

```bash
# Uses defaults (db: kanban, user: kanban, auto-generated password)
kanban-setup --auto

# With explicit credentials via environment variables
KANBAN_DB_NAME=kanban KANBAN_DB_USER=kanban KANBAN_DB_PASSWORD=secret \
  MYSQL_ROOT_PASSWORD=rootpass kanban-setup --auto

# With CLI args
kanban-setup --auto --db-name mydb --db-user myuser --db-password secret
```

### Alternative: shell scripts (from source)

If you cloned the repo instead of using pip:

```bash
./install.sh              # Linux / macOS (interactive)
./install.sh --auto       # Linux / macOS (non-interactive)
.\install.ps1             # Windows (interactive)
.\install.ps1 -Auto       # Windows (non-interactive)
```

| Env Variable | Default | Description |
|---|---|---|
| `KANBAN_DB_NAME` | `kanban` | Database name |
| `KANBAN_DB_USER` | `kanban` | Database user |
| `KANBAN_DB_PASSWORD` | *(auto-generated)* | Database password |
| `KANBAN_DB_HOST` | `localhost` | MySQL host |
| `MYSQL_ROOT_USER` | `root` | MySQL admin user |
| `MYSQL_ROOT_PASSWORD` | *(none — tries socket auth)* | MySQL admin password |

### Manual

```sql
-- As MySQL root user:
CREATE DATABASE kanban CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'kanban'@'%' IDENTIFIED BY 'your_password_here';
GRANT ALL PRIVILEGES ON `kanban`.* TO 'kanban'@'%';
FLUSH PRIVILEGES;
```

Run the migration files in order:

```bash
mysql -u kanban -p kanban < kanban_mcp/migrations/001_initial_schema.sql
mysql -u kanban -p kanban < kanban_mcp/migrations/002_add_fulltext_search.sql
mysql -u kanban -p kanban < kanban_mcp/migrations/003_add_embeddings.sql
mysql -u kanban -p kanban < kanban_mcp/migrations/004_add_cascades_and_indexes.sql
```

Create a `.env` file in your working directory (or the package directory):

```bash
KANBAN_DB_HOST=localhost
KANBAN_DB_USER=kanban
KANBAN_DB_PASSWORD=your_password_here
KANBAN_DB_NAME=kanban
```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `KANBAN_DB_HOST` | No | `localhost` | MySQL server host |
| `KANBAN_DB_USER` | Yes | — | MySQL username |
| `KANBAN_DB_PASSWORD` | Yes | — | MySQL password |
| `KANBAN_DB_NAME` | Yes | — | MySQL database name |
| `KANBAN_DB_POOL_SIZE` | No | `5` | Connection pool size |
| `KANBAN_PROJECT_DIR` | No | — | Override project directory detection |

The `.env` file is loaded from the current working directory and from the package install directory.

## MCP Client Setup

### Claude Desktop

Add to `~/.config/Claude/claude_desktop_config.json` (Linux) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "kanban": {
      "command": "kanban-mcp",
      "env": {
        "KANBAN_DB_HOST": "localhost",
        "KANBAN_DB_USER": "kanban",
        "KANBAN_DB_PASSWORD": "your_password_here",
        "KANBAN_DB_NAME": "kanban"
      }
    }
  }
}
```

### Claude Code

Add to `.claude/settings.json` in your project (or `~/.claude/settings.json` globally):

```json
{
  "mcpServers": {
    "kanban": {
      "command": "kanban-mcp",
      "env": {
        "KANBAN_DB_HOST": "localhost",
        "KANBAN_DB_USER": "kanban",
        "KANBAN_DB_PASSWORD": "your_password_here",
        "KANBAN_DB_NAME": "kanban"
      }
    }
  }
}
```

#### Hooks (recommended)

Add to `.claude/hooks.toml` to inject active kanban items at session start and prompt for updates at session end:

```toml
[[hooks]]
event = "SessionStart"
command = "python3 -m kanban_mcp.hooks.session_start"

[[hooks]]
event = "Stop"
command = "python3 -m kanban_mcp.hooks.stop"
```

## AI Agent Install Guide

Machine-parseable setup instructions for automated installation by AI agents.

### Quick path (recommended for agents)

If MySQL is running and the root user has socket auth or a known password:

```bash
pip install kanban-mcp
# Non-interactive setup — auto-generates password, creates DB, runs migrations, writes .env
kanban-setup --auto --mysql-root-password rootpass
```

To also install semantic search (local ONNX embeddings, ~100MB model download on first use):

```bash
pip install kanban-mcp[semantic]
# or add --with-semantic:
kanban-setup --auto --with-semantic --mysql-root-password rootpass
```

The `--auto` flag skips all prompts. Credentials come from CLI args, env vars, or sensible defaults. The generated `.env` file and stdout output contain the credentials needed for MCP config.

### Manual path (step by step)

#### Step 1: Check prerequisites

```bash
python3 --version   # Requires 3.10+
mysql --version     # Requires MySQL 8.0+
```

#### Step 2: Install kanban-mcp

```bash
pip install kanban-mcp              # base install
pip install kanban-mcp[semantic]    # with semantic search (local ONNX embeddings)
```

#### Step 3: Set up the database

```sql
-- Connect as root: mysql -u root -p
CREATE DATABASE kanban CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'kanban'@'%' IDENTIFIED BY 'GENERATE_A_SECURE_PASSWORD';
GRANT ALL PRIVILEGES ON `kanban`.* TO 'kanban'@'%';
FLUSH PRIVILEGES;
```

```bash
# Run migrations (replace password)
mysql -u kanban -pYOUR_PASSWORD kanban < "$(python3 -c 'import kanban_mcp, os; print(os.path.dirname(kanban_mcp.__file__))')/migrations/001_initial_schema.sql"
mysql -u kanban -pYOUR_PASSWORD kanban < "$(python3 -c 'import kanban_mcp, os; print(os.path.dirname(kanban_mcp.__file__))')/migrations/002_add_fulltext_search.sql"
mysql -u kanban -pYOUR_PASSWORD kanban < "$(python3 -c 'import kanban_mcp, os; print(os.path.dirname(kanban_mcp.__file__))')/migrations/003_add_embeddings.sql"
mysql -u kanban -pYOUR_PASSWORD kanban < "$(python3 -c 'import kanban_mcp, os; print(os.path.dirname(kanban_mcp.__file__))')/migrations/004_add_cascades_and_indexes.sql"
```

#### Step 4: Create .env file

```bash
cat > .env << 'EOF'
KANBAN_DB_HOST=localhost
KANBAN_DB_USER=kanban
KANBAN_DB_PASSWORD=YOUR_PASSWORD
KANBAN_DB_NAME=kanban
EOF
```

#### Step 5: MCP config

For Claude Desktop, add to `~/.config/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "kanban": {
      "command": "kanban-mcp",
      "env": {
        "KANBAN_DB_HOST": "localhost",
        "KANBAN_DB_USER": "kanban",
        "KANBAN_DB_PASSWORD": "YOUR_PASSWORD",
        "KANBAN_DB_NAME": "kanban"
      }
    }
  }
}
```

For Claude Code, add to `.claude/settings.json`:

```json
{
  "mcpServers": {
    "kanban": {
      "command": "kanban-mcp",
      "env": {
        "KANBAN_DB_HOST": "localhost",
        "KANBAN_DB_USER": "kanban",
        "KANBAN_DB_PASSWORD": "YOUR_PASSWORD",
        "KANBAN_DB_NAME": "kanban"
      }
    }
  }
}
```

#### Step 6: Hooks setup

Add to `.claude/hooks.toml`:

```toml
[[hooks]]
event = "SessionStart"
command = "python3 -m kanban_mcp.hooks.session_start"

[[hooks]]
event = "Stop"
command = "python3 -m kanban_mcp.hooks.stop"
```

#### Step 7: Verify installation

```bash
kanban-cli --project /path/to/your/project summary
```

### Adapting for Other AI Tools

**Cursor** — Use `.cursor/hooks.json`:
```json
{
  "hooks": {
    "session_start": ["python3 -m kanban_mcp.hooks.session_start"],
    "session_end": ["python3 -m kanban_mcp.hooks.stop"]
  }
}
```

**Gemini CLI** — Use the `BeforeTool` event hook with the same commands.

**Other MCP clients** — Any tool that supports MCP over STDIO can connect using `kanban-mcp` as the command. The server speaks JSON-RPC 2.0 over stdin/stdout.

## Entry Points

| Command | Description |
|---------|-------------|
| `kanban-mcp` | MCP server (STDIO JSON-RPC) — used by AI clients |
| `kanban-web` | Web UI on localhost:5000 (`--port`, `--host`, `--debug` flags) |
| `kanban-cli` | CLI for manual queries and hook scripts (`--project`, `--format` flags) |
| `kanban-setup` | Database setup wizard (`--auto` for non-interactive, `--with-semantic`) |

## MCP Tools Reference

### Project Management

| Tool | Description |
|------|-------------|
| `set_current_project` | Set the current project context (called at session start with $PWD) |
| `get_current_project` | Get the current project context |
| `project_summary` | Get summary of items by type and status |
| `get_active_items` | Get items in 'in_progress' status |
| `get_todos` | Get items in 'backlog' status — the todo queue |

### Item CRUD

| Tool | Description |
|------|-------------|
| `new_item` | Create a new issue, todo, feature, epic, or diary entry |
| `list_items` | List items with optional type/status/tag filters |
| `get_item` | Get full details of a specific item |
| `edit_item` | Edit an item's title, description, priority, complexity, and/or parent |
| `delete_item` | Permanently delete an item |

### Status Workflow

| Tool | Description |
|------|-------------|
| `advance_status` | Move item to next status in its workflow |
| `revert_status` | Move item to previous status |
| `set_status` | Set item to a specific status |
| `close_item` | Mark item as done/closed |
| `get_status_history` | Get status change history for an item |
| `get_item_metrics` | Get calculated metrics: lead_time, cycle_time, time_in_each_status |

### Progress Updates

| Tool | Description |
|------|-------------|
| `add_update` | Add a progress update, optionally linked to items |
| `get_latest_update` | Get the most recent update |
| `get_updates` | Get recent updates |

### Relationships & Hierarchy

| Tool | Description |
|------|-------------|
| `add_relationship` | Add a relationship (blocks, depends_on, relates_to, duplicates) |
| `remove_relationship` | Remove a relationship |
| `get_item_relationships` | Get all relationships for an item |
| `get_blocking_items` | Get items that block a given item |
| `set_parent` | Set or remove parent relationship |
| `list_children` | Get children of an item (optional recursive) |
| `get_epic_progress` | Get progress stats for an epic |

### Tags

| Tool | Description |
|------|-------------|
| `list_tags` | List all tags with usage counts |
| `add_tag` | Add a tag to an item |
| `remove_tag` | Remove a tag from an item |
| `get_item_tags` | Get all tags assigned to an item |
| `update_tag` | Update tag name and/or color |
| `delete_tag` | Delete a tag from the project |

### File Links & Decisions

| Tool | Description |
|------|-------------|
| `link_file` | Link a file (or file region) to an item |
| `unlink_file` | Remove a file link |
| `get_item_files` | Get all files linked to an item |
| `add_decision` | Add a decision record to an item |
| `get_item_decisions` | Get all decisions for an item |
| `delete_decision` | Delete a decision record |

### Search & Export

| Tool | Description |
|------|-------------|
| `search` | Full-text search across items and updates |
| `semantic_search` | Search by semantic similarity (requires `[semantic]` extra) |
| `find_similar` | Find items similar to a given item, decision, or update |
| `rebuild_embeddings` | Rebuild all embeddings for the project |
| `export_project` | Export project data in JSON, YAML, or Markdown |

### Timeline

| Tool | Description |
|------|-------------|
| `get_item_timeline` | Activity timeline for a specific item |
| `get_project_timeline` | Activity timeline for the entire project |

## Item Types & Workflows

| Type | Workflow |
|------|----------|
| issue | backlog → todo → in_progress → review → done → closed |
| feature | backlog → todo → in_progress → review → done → closed |
| epic | backlog → todo → in_progress → review → done → closed |
| todo | backlog → todo → in_progress → done |
| question | backlog → in_progress → done |
| diary | done (single state) |

## Contributing

```bash
git clone https://github.com/multidimensionalcats/kanban-mcp.git
cd kanban-mcp
python3 -m venv .venv && source .venv/bin/activate
pip install -e .[dev,semantic]

# Run Python tests (requires MySQL with test DB configured)
pytest

# Run frontend JS tests (requires Node.js — optional, only touches web UI code)
npm install && npm test
```

## License

[MIT](LICENSE)
