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
- **Session hooks** — inject active items into AI agent sessions automatically

## Quick Start

**Linux / macOS:**
```bash
curl -fsSL https://raw.githubusercontent.com/multidimensionalcats/kanban-mcp/main/install.sh | bash
```

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/multidimensionalcats/kanban-mcp/main/install.ps1 | iex
```

The install script handles everything: installs pipx and kanban-mcp, detects MySQL (or starts it via Docker), creates the database, runs migrations, and writes your config.

**Already have MySQL running?** The fast path:

```bash
pipx install kanban-mcp[semantic]
kanban-setup
kanban-cli --project . summary
```

## Prerequisites

- **Python 3.10+**
- **MySQL 8.0+** — one of:
  - Local MySQL install
  - Remote MySQL server
  - Docker (the install script can set this up for you)
- **pipx** (recommended) — installed automatically by the install script if missing

## Installation

The install script is the primary install method. It detects your MySQL situation and walks you through setup:

```bash
# Interactive — detects MySQL, offers Docker if needed, installs pipx/kanban-mcp
./install.sh

# Non-interactive with Docker for MySQL
./install.sh --auto --docker

# Non-interactive with remote MySQL
./install.sh --auto --db-host remote.example.com

# Windows equivalents
.\install.ps1
.\install.ps1 -Auto -Docker
.\install.ps1 -Auto -DbHost remote.example.com
```

### Option 1: pipx (recommended)

[pipx](https://pipx.pypa.io/) installs into an isolated virtualenv while making commands globally available. This avoids PEP 668 conflicts on modern distros and ensures hooks work outside the venv.

```bash
pipx install kanban-mcp[semantic]
```

Without semantic search (smaller install):

```bash
pipx install kanban-mcp
```

Upgrade later with:

```bash
pipx upgrade kanban-mcp
```

### Option 2: pip

```bash
pip install --user kanban-mcp[semantic]
```

> **Note:** On modern distros (Debian 12+, Fedora 38+, Arch, Gentoo), bare `pip install` is blocked by [PEP 668](https://peps.python.org/pep-0668/). Use `--user`, `--break-system-packages`, or prefer pipx.

### Option 3: From source (development)

```bash
git clone https://github.com/multidimensionalcats/kanban-mcp.git
cd kanban-mcp
pip install -e .[dev,semantic]
```

> **Note:** If PEP 668 blocks the install, use a venv: `python3 -m venv .venv && source .venv/bin/activate` first. Be aware that hooks run via `/bin/sh`, not the venv Python — you'll need to use full paths to the venv's console scripts in your hook configuration.

### Option 4: Docker (MySQL + web UI)

The install script can start MySQL via Docker for you (`./install.sh --docker` or choose Docker when prompted). If you prefer to run the compose stack manually:

```bash
git clone https://github.com/multidimensionalcats/kanban-mcp.git
cd kanban-mcp
docker compose up
```

This starts MySQL 8.0 and the web UI on port 5000. Migrations run automatically on web container startup. MySQL is exposed on port 3306 so the host-side MCP server can connect. The MCP server still needs a separate install (pipx or pip) since MCP clients spawn it as a subprocess.

Credentials are configurable via environment variables:

```bash
KANBAN_DB_USER=myuser KANBAN_DB_PASSWORD=secret docker compose up
```

## Database Setup

Requires **MySQL 8.0+** running locally (or remotely).

### Automated (interactive)

```bash
kanban-setup
```

Prompts for database name, user, password, and MySQL root credentials, then creates the database, runs migrations, and writes credentials to `~/.config/kanban-mcp/.env`.

> **Note:** `kanban-setup --with-semantic` installs the semantic search Python packages. This is only needed if you installed without `[semantic]` initially (e.g. `pipx install kanban-mcp`). If you already installed with `kanban-mcp[semantic]`, you don't need this flag.

### Automated (non-interactive / AI agents)

The `--auto` flag skips all interactive prompts. Without it, `kanban-setup` will prompt for each value.

```bash
# Minimal — uses socket auth for MySQL root, auto-generates app password
kanban-setup --auto

# With MySQL root password (required if root uses password auth)
kanban-setup --auto --mysql-root-password rootpass

# With explicit credentials via environment variables
KANBAN_DB_NAME=kanban KANBAN_DB_USER=kanban KANBAN_DB_PASSWORD=secret \
  MYSQL_ROOT_PASSWORD=rootpass kanban-setup --auto

# With CLI args
kanban-setup --auto --db-name mydb --db-user myuser --db-password secret
```

> **Note:** If your MySQL root user requires a password (most setups), you must provide `--mysql-root-password` or `MYSQL_ROOT_PASSWORD`. Without it, `kanban-setup --auto` will attempt socket authentication, which fails on most non-local MySQL setups.

### Install script reference

The install scripts can be run from the repo or downloaded standalone:

```bash
./install.sh                          # interactive (detects MySQL, offers Docker)
./install.sh --auto                   # non-interactive, local MySQL
./install.sh --auto --docker          # non-interactive, Docker for MySQL
./install.sh --auto --db-host HOST    # non-interactive, remote MySQL
./install.sh --upgrade                # upgrade existing Docker install

.\install.ps1                         # Windows interactive
.\install.ps1 -Auto                   # Windows non-interactive
.\install.ps1 -Auto -Docker           # Windows Docker
.\install.ps1 -Auto -DbHost HOST      # Windows remote MySQL
.\install.ps1 -Upgrade                # upgrade existing Docker install
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

## Configuration

### Credentials

`kanban-setup` writes database credentials to a `.env` file in the user config directory:

- **Linux/macOS:** `~/.config/kanban-mcp/.env` (or `$XDG_CONFIG_HOME/kanban-mcp/.env`)
- **Windows:** `%APPDATA%\kanban-mcp\.env`

All install methods (pipx, pip, source) use this same location. You can also set credentials via environment variables or your MCP client's `env` block.

**Precedence** (highest to lowest): MCP client `env` block → shell environment variables → `.env` file. In practice, just use one method — the `.env` file from `kanban-setup` is simplest.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `KANBAN_DB_HOST` | No | `localhost` | MySQL server host |
| `KANBAN_DB_USER` | Yes | — | MySQL username |
| `KANBAN_DB_PASSWORD` | Yes | — | MySQL password |
| `KANBAN_DB_NAME` | Yes | — | MySQL database name |
| `KANBAN_DB_POOL_SIZE` | No | `5` | Connection pool size |
| `KANBAN_PROJECT_DIR` | No | — | Override project directory detection |

### MCP Client Setup

The `kanban-mcp` server speaks JSON-RPC 2.0 over stdin/stdout (standard MCP STDIO transport). Any MCP client can use it. If `kanban-setup` already wrote your `.env` file, you only need the command — no `env` block required.

If you need to pass credentials explicitly (e.g. the client doesn't inherit your shell environment), add an `env` block:

```json
"env": {
  "KANBAN_DB_HOST": "localhost",
  "KANBAN_DB_USER": "kanban",
  "KANBAN_DB_PASSWORD": "your_password_here",
  "KANBAN_DB_NAME": "kanban"
}
```

#### Claude Code

Add to `~/.claude.json` (global) or `.mcp.json` (per-project):

```json
{
  "mcpServers": {
    "kanban": {
      "command": "kanban-mcp"
    }
  }
}
```

#### Claude Desktop

Add to `~/.config/Claude/claude_desktop_config.json` (Linux) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "kanban": {
      "command": "kanban-mcp"
    }
  }
}
```

#### Gemini CLI

Add to `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "kanban": {
      "command": "kanban-mcp"
    }
  }
}
```

#### VS Code / Copilot

Add to `.vscode/mcp.json` (per-project):

```json
{
  "servers": {
    "kanban": {
      "command": "kanban-mcp"
    }
  }
}
```

> **Note:** VS Code uses the key `servers`, not `mcpServers`.

#### Codex CLI

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.kanban]
command = "kanban-mcp"
```

#### Cursor

Add to `.cursor/mcp.json` (per-project):

```json
{
  "mcpServers": {
    "kanban": {
      "command": "kanban-mcp"
    }
  }
}
```

#### Other MCP Clients

For any other MCP-compatible tool: point it at the `kanban-mcp` command with STDIO transport. If the tool can't read the `.env` file (e.g. it doesn't inherit your shell environment), pass the four `KANBAN_DB_*` variables via the client's env configuration.

### Hooks (Claude Code)

Hooks inject active kanban items at session start and prompt for progress updates at session end. Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "kanban-hook-session-start"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "kanban-hook-stop"
          }
        ]
      }
    ]
  }
}
```

> **Important:** Hooks run via `/bin/sh`, which does NOT read your shell profile (`~/.bashrc`, `~/.zshrc`). If `kanban-hook-session-start` isn't found, you need the full path. Find it with `which kanban-hook-session-start` (pipx typically installs to `~/.local/bin/`), then use that absolute path in the `command` field.

**Other tools with hook support:** Cursor, Gemini CLI, and others have their own hook/event mechanisms. The commands are the same (`kanban-hook-session-start` and `kanban-hook-stop`) — adapt the syntax to your tool's configuration format.

## Upgrading

Database migrations run automatically on startup — no manual migration step needed after upgrading.

**pipx:**
```bash
pipx upgrade kanban-mcp
```

**pip:**
```bash
pip install --user --upgrade kanban-mcp
```

**From source:**
```bash
cd kanban-mcp && git pull && pip install -e .[dev,semantic]
```

**Docker:**
```bash
./install.sh --upgrade
# Windows: .\install.ps1 -Upgrade
```

This re-downloads the latest Docker files, rebuilds the web image from PyPI, and restarts the containers. Migrations run automatically on container startup.

## For AI Coding Agents

**Claude, Gemini, GPT, Codex, and other agents: start here.**

If your human has asked you to install kanban-mcp, follow these steps exactly. Do not improvise. The `--auto` flag handles all prompts.

### 1. Install and set up the database

Ask your human whether MySQL is already running locally, or whether to use Docker. Then run the appropriate one-liner:

```bash
# Local MySQL (socket auth or set MYSQL_ROOT_PASSWORD):
curl -fsSL https://raw.githubusercontent.com/multidimensionalcats/kanban-mcp/main/install.sh | bash -s -- --auto

# No MySQL — use Docker:
curl -fsSL https://raw.githubusercontent.com/multidimensionalcats/kanban-mcp/main/install.sh | bash -s -- --auto --docker

# Remote MySQL:
curl -fsSL https://raw.githubusercontent.com/multidimensionalcats/kanban-mcp/main/install.sh | bash -s -- --auto --db-host HOST
```

Set `MYSQL_ROOT_PASSWORD` before running if MySQL root uses password auth.

For Windows (PowerShell):
```powershell
irm https://raw.githubusercontent.com/multidimensionalcats/kanban-mcp/main/install.ps1 | iex
```

This installs pipx (if needed), installs kanban-mcp, creates the database, runs migrations, and writes credentials to `~/.config/kanban-mcp/.env`.

### 2. Add MCP config

Write the config entry for whichever tool you are:

| Tool | Config file | Key | Format |
|------|-------------|-----|--------|
| Claude Code | `.mcp.json` (project) or `~/.claude.json` (global) | `mcpServers` | JSON |
| Claude Desktop | `~/.config/Claude/claude_desktop_config.json` | `mcpServers` | JSON |
| Gemini CLI | `~/.gemini/settings.json` | `mcpServers` | JSON |
| VS Code / Copilot | `.vscode/mcp.json` | `servers` | JSON |
| Cursor | `.cursor/mcp.json` | `mcpServers` | JSON |
| Codex CLI | `~/.codex/config.toml` | `[mcp_servers.kanban]` | TOML |

The server entry (JSON example):

```json
{
  "kanban": {
    "command": "kanban-mcp"
  }
}
```

No `env` block is needed — credentials are read from `~/.config/kanban-mcp/.env` which `kanban-setup` created in step 2.

### 3. Verify

```bash
kanban-cli --project /path/to/humans/project summary
```

### 4. Hooks (optional, Claude Code only)

Hooks inject active kanban items at session start. The commands run via `/bin/sh` which does not read shell profiles, so you must use absolute paths. Find them:

```bash
which kanban-hook-session-start
which kanban-hook-stop
```

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      { "hooks": [{ "type": "command", "command": "ABSOLUTE_PATH/kanban-hook-session-start" }] }
    ],
    "Stop": [
      { "hooks": [{ "type": "command", "command": "ABSOLUTE_PATH/kanban-hook-stop" }] }
    ]
  }
}
```

Replace `ABSOLUTE_PATH` with the actual paths from `which`.

## Entry Points

| Command | Description |
|---------|-------------|
| `kanban-mcp` | MCP server (STDIO JSON-RPC) — used by AI clients |
| `kanban-web` | Web UI on localhost:5000 (`--port`, `--host`, `--debug` flags) |
| `kanban-cli` | CLI for manual queries and hook scripts (`--project`, `--format` flags) |
| `kanban-setup` | Database setup wizard (`--auto` for non-interactive, `--with-semantic`) |
| `kanban-hook-session-start` | Session start hook — injects active items into agent sessions |
| `kanban-hook-stop` | Session stop hook — prompts for progress updates |

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
