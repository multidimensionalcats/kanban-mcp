# kanban-mcp

A database-backed kanban board that AI coding agents use via [MCP](https://modelcontextprotocol.io/) (Model Context Protocol). Track issues, features, todos, epics, and diary entries across all your projects — with a web UI for humans and 40+ tools for agents.

![Kanban board overview](webui.png)

<details>
<summary>More screenshots</summary>

![Activity timeline](webui-timeline.png)
![New item dialog](webui-issue.png)

</details>

## What It Does

- **Persistent project tracking** — issues, features, todos, epics, questions, diary entries stored in SQLite (default) or MySQL/MariaDB
- **Status workflows** — each item type has its own progression (backlog → todo → in_progress → review → done → closed)
- **Relationships & epics** — parent/child hierarchies, blocking relationships, epic progress tracking
- **Tags, decisions, file links** — attach metadata to any item
- **Semantic search** — find similar items using local ONNX embeddings (optional; downloads [nomic-embed-text-v1.5](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5) from HuggingFace on first use, ~140MB — the first query will block until download completes)
- **Activity timeline** — unified view of status changes, decisions, updates, and git commits
- **Export** — JSON, YAML, or Markdown output with filters
- **Web UI** — browser-based board at localhost:5000
- **Session hooks** — inject active items into AI agent sessions automatically

## Quick Start

Requires **Python 3.10+**.

**Linux / macOS:**
```bash
curl -fsSL https://raw.githubusercontent.com/multidimensionalcats/kanban-mcp/main/install.sh | bash
```

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/multidimensionalcats/kanban-mcp/main/install.ps1 | iex
```

The script prompts interactively (backend choice, etc.) then installs pipx
and kanban-mcp, sets up the database, runs migrations, and prints your MCP
config. SQLite is the default — just press Enter. No database server required.

**Want MySQL/MariaDB instead?** Add `--mysql` (or `-MySQL` on Windows):
```bash
curl -fsSL https://raw.githubusercontent.com/multidimensionalcats/kanban-mcp/main/install.sh | bash -s -- --auto --mysql
```

**Manual install (no script):**
```bash
pipx install kanban-mcp
kanban-cli --project "$(pwd)" summary   # SQLite DB auto-created on first run
```
Then add the MCP server to your AI client — see [MCP Client Setup](#mcp-client-setup).

## Prerequisites

- **Python 3.10+**
- **pipx** (recommended) — installed automatically by the install script if missing
- **MySQL 8.0+ or MariaDB 11+** *(optional)* — only needed if you choose MySQL over the default SQLite backend

## Installation

The [Quick Start](#quick-start) one-liner is the fastest path. Below are alternative install methods and additional options.

### Option 1: pipx (recommended)

[pipx](https://pipx.pypa.io/) installs into an isolated virtualenv while making commands globally available. This avoids PEP 668 conflicts on modern distros and ensures hooks work outside the venv.

```bash
# SQLite backend (default, zero dependencies)
pipx install kanban-mcp

# With semantic search
pipx install kanban-mcp[semantic]

# With MySQL backend
pipx install kanban-mcp[mysql]

# Everything (MySQL + semantic)
pipx install kanban-mcp[full]
```

The SQLite database is created automatically on first run — no extra setup needed. For MySQL, see [Database Setup](#database-setup).

Upgrade later with:

```bash
pipx upgrade kanban-mcp
```

### Option 2: pip

```bash
pip install --user kanban-mcp
```

> **Note:** On modern distros (Debian 12+, Fedora 38+, Arch, Gentoo), bare `pip install` is blocked by [PEP 668](https://peps.python.org/pep-0668/). Use `--user`, `--break-system-packages`, or prefer pipx.

### Option 3: From source (development)

```bash
git clone https://github.com/multidimensionalcats/kanban-mcp.git
cd kanban-mcp
pip install -e .[dev]
```

> **Note:** If PEP 668 blocks the install, use a venv: `python3 -m venv .venv && source .venv/bin/activate` first. Be aware that hooks run via `/bin/sh`, not the venv Python — you'll need to use full paths to the venv's console scripts in your hook configuration.

### Option 4: Docker (MySQL/MariaDB + web UI)

> **Note:** Docker compose runs MySQL/MariaDB, not SQLite. Use this if you want a containerized MySQL setup.

The install script can start MySQL/MariaDB via Docker for you (`./install.sh --auto --mysql --docker` or choose Docker when prompted). To run the compose stack manually:

1. **Start the containers** (MySQL 8.0 + web UI on port 5000):
   ```bash
   git clone https://github.com/multidimensionalcats/kanban-mcp.git
   cd kanban-mcp
   docker compose up
   ```
   Migrations run automatically on web container startup. Credentials are configurable: `KANBAN_DB_USER=myuser KANBAN_DB_PASSWORD=secret docker compose up`

2. **Install the MCP server on the host** — Docker only provides the database and web UI. MCP clients spawn the server as a subprocess, so it must be installed locally:
   ```bash
   pipx install kanban-mcp[mysql]
   ```

3. **Configure your MCP client** — see [MCP Client Setup](#mcp-client-setup). The database is exposed on port 3306 so the host-side MCP server can connect.

## Database Setup

kanban-mcp uses **SQLite by default** — no setup required. The database
file is created automatically on first run at `~/.local/share/kanban-mcp/kanban.db`
(or `$XDG_DATA_HOME/kanban-mcp/kanban.db`). You do not need to run `kanban-setup`
for SQLite — it is only necessary if you want a custom database path or MySQL.

`kanban-setup --auto` defaults to SQLite. To choose a custom path:

```bash
kanban-setup --auto --backend sqlite --sqlite-path /path/to/db
```

> **Note:** `kanban-setup --with-semantic` installs the semantic search Python packages. This is only needed if you installed without `[semantic]` initially (e.g. `pipx install kanban-mcp`). If you already installed with `kanban-mcp[semantic]`, you don't need this flag. Works with any backend.

### MySQL/MariaDB (optional)

If you need MySQL/MariaDB instead of SQLite:

#### Automated (interactive)

```bash
kanban-setup
```

Prompts for database name, user, password, and MySQL/MariaDB root credentials (including root password), then creates the database, runs migrations, and writes credentials to `~/.config/kanban-mcp/.env`.

> **Note:** On Debian/Ubuntu, `default-mysql-server` installs MariaDB, which defaults to `auth_socket` for the root user. Socket auth only works when the OS user matches the MySQL user (i.e. running as OS root). For non-root users, provide the MySQL root password when prompted — this is the normal path.

#### Automated (non-interactive / AI agents)

The `--auto` flag skips all interactive prompts. Without it, `kanban-setup` will prompt for each value.

```bash
# With root password (most common)
kanban-setup --auto --backend mysql --mysql-root-password rootpass

# With explicit credentials via environment variables
KANBAN_DB_NAME=kanban KANBAN_DB_USER=kanban KANBAN_DB_PASSWORD=secret \
  MYSQL_ROOT_PASSWORD=rootpass kanban-setup --auto --backend mysql

# With CLI args
kanban-setup --auto --backend mysql --db-name mydb --db-user myuser --db-password secret

# Socket auth (only works when OS user matches MySQL user, e.g. running as root)
kanban-setup --auto --backend mysql
```

> **Important:** `MYSQL_ROOT_PASSWORD` is **required** for non-interactive use unless you are running as OS root. Socket auth (`auth_socket`) only works when the OS user matches the MySQL user — this is uncommon outside of CI or Docker. On Debian/Ubuntu, MariaDB defaults root to `auth_socket` — set `MYSQL_ROOT_PASSWORD` or use the manual SQL setup below.

### Install script reference

The install scripts can be run from the repo or downloaded standalone:

```bash
./install.sh                                        # interactive (asks backend, installs pipx/kanban-mcp)
./install.sh --auto                                  # non-interactive, SQLite (default, zero config)
./install.sh --auto --mysql                          # non-interactive, local MySQL/MariaDB (socket auth)
MYSQL_ROOT_PASSWORD=rootpass ./install.sh --auto --mysql  # non-interactive, MySQL with root password
./install.sh --auto --mysql --docker                 # non-interactive, MySQL via Docker
./install.sh --auto --mysql --db-host HOST           # non-interactive, remote MySQL
./install.sh --upgrade                               # upgrade existing Docker install

.\install.ps1                         # Windows interactive
.\install.ps1 -Auto                   # Windows non-interactive (SQLite)
.\install.ps1 -Auto -MySQL            # Windows MySQL
.\install.ps1 -Auto -MySQL -Docker    # Windows MySQL via Docker
.\install.ps1 -Auto -MySQL -DbHost HOST  # Windows remote MySQL
.\install.ps1 -Upgrade                # upgrade existing Docker install
```

| Env Variable | Default | Description |
|---|---|---|
| `KANBAN_BACKEND` | `sqlite` | Backend: `sqlite` or `mysql` |
| `KANBAN_SQLITE_PATH` | `$XDG_DATA_HOME/kanban-mcp/kanban.db` | SQLite database file path |
| `KANBAN_DB_NAME` | `kanban` | MySQL database name |
| `KANBAN_DB_USER` | `kanban` | Database user |
| `KANBAN_DB_PASSWORD` | *(auto-generated)* | Database password |
| `KANBAN_DB_HOST` | `localhost` | Database host |
| `KANBAN_DB_PORT` | `3306` | Database port |
| `MYSQL_ROOT_USER` | `root` | Database admin user |
| `MYSQL_ROOT_PASSWORD` | *(none — tries socket auth)* | Database admin password (**required** unless running as OS root) |

#### Manual

Manual setup is a good alternative if database root auth is problematic (e.g. socket auth issues, restricted access).

```sql
-- As MySQL/MariaDB root user:
CREATE DATABASE kanban CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'kanban'@'localhost' IDENTIFIED BY 'your_password_here';
CREATE USER 'kanban'@'%' IDENTIFIED BY 'your_password_here';
GRANT ALL PRIVILEGES ON `kanban`.* TO 'kanban'@'localhost';
GRANT ALL PRIVILEGES ON `kanban`.* TO 'kanban'@'%';
FLUSH PRIVILEGES;
```

> **Note:** On MariaDB, `'kanban'@'%'` does not match localhost socket connections — you need both the `@'localhost'` and `@'%'` users.

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

> **Warning:** If you previously used MySQL and switch to SQLite, remove or rename the old `.env` file at `~/.config/kanban-mcp/.env`. Leftover `KANBAN_DB_USER`/`KANBAN_DB_PASSWORD`/`KANBAN_DB_NAME` values will silently trigger MySQL auto-detection. Alternatively, set `KANBAN_BACKEND=sqlite` explicitly to override.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `KANBAN_BACKEND` | No | *(auto-detect)* | Force backend: `sqlite` or `mysql`. Auto-detect uses MySQL if `KANBAN_DB_USER`, `KANBAN_DB_PASSWORD`, and `KANBAN_DB_NAME` are all set, otherwise SQLite |
| `KANBAN_SQLITE_PATH` | No | `$XDG_DATA_HOME/kanban-mcp/kanban.db` | SQLite database file path |
| `KANBAN_DB_HOST` | No | `localhost` | MySQL database server host |
| `KANBAN_DB_PORT` | No | `3306` | MySQL database server port |
| `KANBAN_DB_USER` | Yes (MySQL only) | — | MySQL database username |
| `KANBAN_DB_PASSWORD` | Yes (MySQL only) | — | MySQL database password |
| `KANBAN_DB_NAME` | Yes (MySQL only) | — | MySQL database name |
| `KANBAN_DB_POOL_SIZE` | No | `5` | MySQL connection pool size |
| `KANBAN_PROJECT_DIR` | No | — | Override project directory detection |
| `KANBAN_WEB_PORT` | No | `5000` | Web UI port (`kanban-web`) |
| `KANBAN_WEB_HOST` | No | `127.0.0.1` | Web UI bind address (`kanban-web`) |

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

For any other MCP-compatible tool: point it at the `kanban-mcp` command with STDIO transport. With the default SQLite backend, no env configuration is needed. If using MySQL and the tool can't read the `.env` file (e.g. it doesn't inherit your shell environment), pass the `KANBAN_DB_*` variables via the client's env configuration.

### Hooks

Hooks are what make the agent use the board automatically. Without them, the agent only interacts with kanban-mcp when you explicitly ask it to.

Two hooks ship as console scripts, installed alongside `kanban-mcp`:

**`kanban-hook-session-start`** — Runs at session start. Reads the project directory from the hook's stdin JSON (`cwd` field), looks up the project in the database, and prints any in-progress items. This output gets injected into the conversation context, so the agent knows what's active without being told.

**`kanban-hook-stop`** — Runs at session end. Lists items still in progress and suggests creating a diary entry, updating statuses, or adding progress notes. This nudges the agent (and you) to keep the board current.

Both hooks exit silently if the project isn't tracked or the database is unreachable — they never block a session.

#### Which clients support hooks?

| Client | Session hooks? | Config location |
|--------|---------------|-----------------|
| Claude Code | Yes | `~/.claude/settings.json` |
| Gemini CLI | Yes | `~/.gemini/settings.json` |
| VS Code Copilot | Yes (preview) | `~/.claude/settings.json`¹ or `.github/hooks/*.json` |
| Copilot CLI | Yes | Hook config files |
| Cursor | Yes (plugin primitive) | Hook config |

¹ VS Code Copilot reads Claude Code's hook configuration — if you already configured hooks for Claude Code, VS Code Copilot will use them too.

Claude Code, Gemini CLI, and VS Code Copilot all use the same hook format. Gemini CLI also sets `CLAUDE_PROJECT_DIR` as a compatibility alias, so the kanban hooks work across all three without modification.

#### Configuration

Hooks run via `/bin/sh` (Linux/macOS) or `cmd` (Windows), which do **not** read shell profiles — you must use absolute paths.

Find your paths:
```bash
# Linux/macOS
which kanban-hook-session-start   # typically ~/.local/bin/kanban-hook-session-start
which kanban-hook-stop
```
```powershell
# Windows
Get-Command kanban-hook-session-start | Select-Object -ExpandProperty Source
# typically C:\Users\<you>\pipx\venvs\kanban-mcp\Scripts\kanban-hook-session-start.exe
```

Merge into your client's settings file (`~/.claude/settings.json` for Claude Code and VS Code Copilot, `~/.gemini/settings.json` for Gemini CLI):

Linux/macOS:
```json
{
  "hooks": {
    "SessionStart": [
      { "hooks": [{ "type": "command", "command": "/home/you/.local/bin/kanban-hook-session-start" }] }
    ],
    "Stop": [
      { "hooks": [{ "type": "command", "command": "/home/you/.local/bin/kanban-hook-stop" }] }
    ]
  }
}
```

Windows:
```json
{
  "hooks": {
    "SessionStart": [
      { "hooks": [{ "type": "command", "command": "C:\\Users\\you\\pipx\\venvs\\kanban-mcp\\Scripts\\kanban-hook-session-start.exe" }] }
    ],
    "Stop": [
      { "hooks": [{ "type": "command", "command": "C:\\Users\\you\\pipx\\venvs\\kanban-mcp\\Scripts\\kanban-hook-stop.exe" }] }
    ]
  }
}
```

If you already have hooks configured, add the kanban entries to your existing arrays — don't replace them.

> **Tip:** `install.sh` and `install.ps1` print a ready-to-use config snippet with your resolved paths after setup completes.

## Usage

### First session

Once installed and configured, open your AI agent in a project directory. The first time you do this:

1. The session start hook fires but exits silently (it doesn't know about this project yet)
2. The agent needs to call `set_current_project` with your working directory's **absolute path** — this auto-creates the project in the database
3. From this point, all kanban tools work against this project
4. At session end, the stop hook lists any in-progress items and suggests logging progress

On subsequent sessions in the same directory, the start hook injects your active items into the conversation automatically — the agent picks up where you left off.

There is no "create project" command. Projects are created implicitly the first time `set_current_project` is called for a directory. If the agent doesn't call it on its own, ask it to — or the hooks will handle project context once the project exists in the database.

> **Note:** Paths are resolved (symlinks, `.`, `..`) before hashing, so `--project .` and `--project $PWD` refer to the same project. The same applies to `set_current_project`.

### Three interfaces

kanban-mcp provides three ways to interact with the same data:

**MCP tools** — 40+ tools the AI agent calls during conversation. This is the primary interface. The agent creates items, tracks dependencies, advances statuses, and logs progress as part of your normal workflow. You don't need to tell it to — the session hooks provide context and the agent uses the tools naturally.

**Web UI** — a browser-based kanban board for humans.

```bash
kanban-web                    # http://127.0.0.1:5000
kanban-web --port 8080        # custom port
kanban-web --host 0.0.0.0     # network-accessible (no auth — use with care)
KANBAN_WEB_PORT=8080 kanban-web  # port via env var
```

`kanban-web` runs in the foreground. To run it persistently, use a process manager (e.g. `systemd`, `screen`, `tmux`) or the Docker compose stack which includes the web UI.

> **macOS note:** Port 5000 is used by AirPlay Receiver on modern macOS. If `kanban-web` fails to bind, use `--port 5001` or set `KANBAN_WEB_PORT=5001`.

The board shows all status columns (backlog → todo → in_progress → review → done → closed) with drag-and-drop between them. Use the project dropdown in the header to switch between projects. Cards show priority, tags, epic membership, blocking relationships, and progress bars for epics.

**CLI** — `kanban-cli` for terminal queries, scripts, and exports. Every command takes `--project PATH` (the same directory path you'd use with your agent) and an optional `--format {text,json}`.

### CLI reference

All commands take `--project PATH` with the **absolute path** to your project directory, and an optional `--format {text,json}`.

```bash
# What's currently being worked on?
kanban-cli --project /path/to/project active

# What's in the backlog?
kanban-cli --project /path/to/project todos

# Project overview — counts by type and status
kanban-cli --project /path/to/project summary

# Search items and updates
kanban-cli --project /path/to/project search "authentication"

# Semantic search (requires [semantic] extra)
kanban-cli --project /path/to/project semantic-search "auth problems" --limit 5

# Export the full board
kanban-cli --project /path/to/project export --format markdown
kanban-cli --project /path/to/project export --format json --metrics --relationships

# Get children of an epic
kanban-cli --project /path/to/project children 42 --recursive

# Context dump (what the session hooks use internally)
kanban-cli --project /path/to/project context

# Rebuild embeddings after bulk changes
kanban-cli --project /path/to/project rebuild-embeddings
```

> **Tip:** Paths are resolved (symlinks, `.`, `..`) before hashing, so `--project .` and `--project $PWD` refer to the same project.

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
cd kanban-mcp && git pull && pip install -e .[dev]
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

The default path uses SQLite — zero config, no database server needed:

```bash
curl -fsSL https://raw.githubusercontent.com/multidimensionalcats/kanban-mcp/main/install.sh | bash -s -- --auto
```

If your human specifically wants MySQL/MariaDB, add `--mysql`:

```bash
# MySQL via Docker:
curl -fsSL https://raw.githubusercontent.com/multidimensionalcats/kanban-mcp/main/install.sh | bash -s -- --auto --mysql --docker

# Local MySQL (set MYSQL_ROOT_PASSWORD if needed):
curl -fsSL https://raw.githubusercontent.com/multidimensionalcats/kanban-mcp/main/install.sh | bash -s -- --auto --mysql

# Remote MySQL:
curl -fsSL https://raw.githubusercontent.com/multidimensionalcats/kanban-mcp/main/install.sh | bash -s -- --auto --mysql --db-host HOST
```

For Windows (PowerShell — downloaded to a file because `irm | iex` doesn't support passing flags like `-Auto`):
```powershell
irm https://raw.githubusercontent.com/multidimensionalcats/kanban-mcp/main/install.ps1 -OutFile install.ps1
.\install.ps1 -Auto
```

This installs pipx (if needed), installs kanban-mcp, creates the database, runs migrations, and writes config to `~/.config/kanban-mcp/.env`.

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

No `env` block is needed — credentials are read from `~/.config/kanban-mcp/.env` which the install script created in step 1.

### 3. Verify

```bash
kanban-cli --project /path/to/humans/project summary
```

### 4. Configure hooks (recommended)

Hooks are what make you use the board automatically. Without them, you only interact with kanban-mcp when the human asks you to.

- **`kanban-hook-session-start`** — Runs at session start. Reads the project directory, queries in-progress items, and injects them into the conversation so you know what's active.
- **`kanban-hook-stop`** — Runs at session end. Lists items still in progress and reminds you to update statuses or create a diary entry.

If your client supports hooks (Claude Code, Gemini CLI, VS Code Copilot, Copilot CLI, Cursor): resolve the absolute paths via `which`, read your client's hook config file, merge the kanban hook entries (preserving any existing hooks), and write back. Do not overwrite other hook entries. See the [Hooks](#hooks) section above for per-client config formats and paths.

## Entry Points

| Command | Description |
|---------|-------------|
| `kanban-mcp` | MCP server (STDIO JSON-RPC) — used by AI clients |
| `kanban-web` | Web UI on localhost:5000 (`--port`, `--host`, `--debug` flags; env: `KANBAN_WEB_PORT`, `KANBAN_WEB_HOST`) |
| `kanban-cli` | CLI for manual queries and hook scripts (`--project`, `--format` flags) |
| `kanban-setup` | Database setup wizard (see flags below) |
| `kanban-hook-session-start` | Session start hook — injects active items into agent sessions |
| `kanban-hook-stop` | Session stop hook — prompts for progress updates |

### `kanban-setup` flags

| Flag | Description |
|------|-------------|
| `--auto` | Non-interactive mode (skip all prompts, use defaults) |
| `--backend {sqlite,mysql}` | Choose backend (default: `sqlite`) |
| `--sqlite-path PATH` | Custom SQLite database file path |
| `--db-name NAME` | MySQL database name (default: `kanban`) |
| `--db-user USER` | MySQL database user (default: `kanban`) |
| `--db-password PASS` | MySQL database password (default: auto-generated) |
| `--db-host HOST` | MySQL database host (default: `localhost`) |
| `--db-port PORT` | MySQL database port (default: `3306`) |
| `--mysql-root-password PASS` | MySQL root password for creating the database |
| `--with-semantic` | Install semantic search Python packages |
| `--docker` | Start MySQL via Docker |

## MCP Tools Reference

### Project Management

| Tool | Description |
|------|-------------|
| `set_current_project` | Set the current project context (called at session start with $PWD) |
| `get_current_project` | Get the current project context |
| `project_summary` | Get summary of items by type and status |
| `get_active_items` | Get items in 'in_progress' status |
| `get_todos` | Get items in 'backlog' status |

### Item CRUD

| Tool | Description |
|------|-------------|
| `new_item` | Create a new issue, todo, feature, epic, question, or diary entry |
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
pip install -e .[dev]

# Run tests (uses in-memory SQLite by default, no setup needed)
pytest

# Run tests against MySQL (requires MySQL/MariaDB running)
KANBAN_BACKEND=mysql KANBAN_DB_HOST=localhost KANBAN_DB_USER=kanban KANBAN_DB_PASSWORD=secret KANBAN_DB_NAME=kanban_test pytest

# Run frontend JS tests (requires Node.js — optional, only touches web UI code)
npm install && npm test
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release notes. Check your installed version with:

```bash
pipx list | grep kanban-mcp
# or
pip show kanban-mcp
```

## License

[MIT](LICENSE)
