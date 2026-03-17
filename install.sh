#!/bin/bash
#
# kanban-mcp install script
# Installs kanban-mcp (via pipx), chooses a database backend (SQLite by
# default, or MySQL/MariaDB), and runs kanban-setup.
#
# Interactive (default):
#   ./install.sh
#   curl -fsSL https://raw.githubusercontent.com/.../install.sh | bash
#
# Non-interactive:
#   ./install.sh --auto                        # SQLite (zero config)
#   ./install.sh --auto --mysql                # local MySQL, socket auth
#   ./install.sh --auto --docker               # MySQL via Docker
#   ./install.sh --auto --db-host remote.host  # remote MySQL
#
# Options:
#   --auto            Non-interactive mode (no prompts)
#   --mysql           Use MySQL/MariaDB backend (default is SQLite)
#   --docker          Use Docker for MySQL (implies --mysql)
#   --db-host HOST    MySQL host (implies --mysql; default: localhost)
#   --with-semantic   Also install semantic search dependencies
#   --upgrade         Upgrade existing Docker install (re-downloads files, rebuilds, restarts)
#   --uninstall       Remove kanban-mcp (package, config, optionally DB and Docker data)
#
# Environment variables (for --auto mode):
#   KANBAN_DB_NAME, KANBAN_DB_USER, KANBAN_DB_PASSWORD, KANBAN_DB_HOST,
#   MYSQL_ROOT_USER, MYSQL_ROOT_PASSWORD

set -euo pipefail

GITHUB_RAW="https://raw.githubusercontent.com/multidimensionalcats/kanban-mcp/main"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/kanban-mcp"

# Ensure common install locations are on PATH (pipx, pip --user)
export PATH="$HOME/.local/bin:$PATH"

AUTO=false
USE_DOCKER=false
USE_MYSQL=false
WITH_SEMANTIC=false
UPGRADE=false
UNINSTALL=false
DB_HOST_ARG=""

for arg in "$@"; do
    case "$arg" in
        --auto) AUTO=true ;;
        --docker) USE_DOCKER=true ;;
        --mysql) USE_MYSQL=true ;;
        --with-semantic) WITH_SEMANTIC=true ;;
        --upgrade) UPGRADE=true ;;
        --uninstall) UNINSTALL=true ;;
        --db-host)
            # handled below with shift
            ;;
        --help|-h)
            echo "Usage: ./install.sh [--auto] [--mysql] [--docker] [--db-host HOST] [--with-semantic] [--upgrade] [--uninstall]"
            echo ""
            echo "Options:"
            echo "  --auto            Non-interactive mode (uses env vars or defaults)"
            echo "  --mysql           Use MySQL/MariaDB backend (default is SQLite)"
            echo "  --docker          Use Docker for MySQL (implies --mysql)"
            echo "  --db-host HOST    MySQL host (implies --mysql; default: localhost)"
            echo "  --with-semantic   Also install semantic search dependencies"
            echo "  --upgrade         Upgrade an existing Docker installation"
            echo "  --uninstall       Remove kanban-mcp (package, config, optionally DB and Docker data)"
            echo ""
            echo "Environment variables (for --auto mode):"
            echo "  KANBAN_DB_NAME       Database name (default: kanban)"
            echo "  KANBAN_DB_USER       Database user (default: kanban)"
            echo "  KANBAN_DB_PASSWORD   Database password (auto-generated if unset)"
            echo "  KANBAN_DB_HOST       Database host (default: localhost)"
            echo "  MYSQL_ROOT_USER      MySQL admin user for setup (default: root)"
            echo "  MYSQL_ROOT_PASSWORD  MySQL admin password (prompted if unset in interactive mode)"
            exit 0
            ;;
    esac
done

# Parse --db-host with its value
while [[ $# -gt 0 ]]; do
    case "$1" in
        --db-host)
            DB_HOST_ARG="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

echo "=== kanban-mcp Install ==="
echo

# ─── Docker file helpers (needed by both --upgrade and fresh install) ─

get_installed_version() {
    # Get the installed kanban-mcp version for tag-pinned downloads.
    # Uses python3 directly (PYTHON may not be set yet in --upgrade path).
    python3 -c "from importlib.metadata import version; print(version('kanban-mcp'))" 2>/dev/null || echo ""
}

is_local_checkout() {
    [ -f "pyproject.toml" ] && grep -q 'name = "kanban-mcp"' pyproject.toml 2>/dev/null
}

download_docker_files() {
    local docker_dir="$CONFIG_DIR/docker"
    mkdir -p "$docker_dir"

    # Prefer local files from a checkout (guaranteed version match)
    if is_local_checkout; then
        echo "Copying Docker files from local checkout..."
        cp docker-compose.yml "$docker_dir/docker-compose.yml"
        cp Dockerfile "$docker_dir/Dockerfile"
        cp entrypoint.sh "$docker_dir/entrypoint.sh"
    else
        # Pin to installed version tag, fall back to main
        local ver
        ver=$(get_installed_version)
        local raw_url="$GITHUB_RAW"
        if [ -n "$ver" ]; then
            local tag_url="https://raw.githubusercontent.com/multidimensionalcats/kanban-mcp/v${ver}"
            # Verify the tag exists before using it
            if curl -fsSL --head "${tag_url}/Dockerfile" &>/dev/null; then
                raw_url="$tag_url"
                echo "Downloading Docker files (pinned to v${ver})..."
            else
                echo "Downloading Docker files (from main, tag v${ver} not found)..."
            fi
        else
            echo "Downloading Docker files..."
        fi
        curl -fsSL "$raw_url/docker-compose.yml" -o "$docker_dir/docker-compose.yml"
        curl -fsSL "$raw_url/Dockerfile" -o "$docker_dir/Dockerfile"
        curl -fsSL "$raw_url/entrypoint.sh" -o "$docker_dir/entrypoint.sh"
    fi

    chmod +x "$docker_dir/entrypoint.sh"
    echo "Docker files installed to $docker_dir"
}

# ─── Upgrade path (early exit) ────────────────────────────────────

if [ "$UPGRADE" = true ]; then
    docker_dir="$CONFIG_DIR/docker"
    compose_file="$docker_dir/docker-compose.yml"

    if [ ! -f "$compose_file" ]; then
        echo "Error: No Docker installation found at $docker_dir"
        echo "For pipx upgrades:  pipx upgrade kanban-mcp"
        echo "For fresh install:  ./install.sh --docker"
        exit 1
    fi

    if ! command -v docker &>/dev/null || ! docker compose version &>/dev/null; then
        echo "Error: Docker or docker compose not found."
        exit 1
    fi

    echo "Upgrading Docker installation..."
    echo

    # Upgrade the pipx package first so version detection is accurate
    echo "Upgrading kanban-mcp package..."
    if command -v pipx &>/dev/null; then
        pipx upgrade kanban-mcp 2>/dev/null || pipx upgrade "kanban-mcp[mysql]" 2>/dev/null || true
    fi
    echo

    # Re-download Docker files pinned to the installed version
    download_docker_files
    echo

    # Load .env for compose
    if [ -f "$CONFIG_DIR/.env" ]; then
        set -a
        # shellcheck source=/dev/null
        source "$CONFIG_DIR/.env"
        set +a
    fi

    # Rebuild and restart
    echo "Rebuilding web image..."
    docker compose -f "$compose_file" build --no-cache
    echo

    echo "Restarting services..."
    docker compose -f "$compose_file" up -d
    echo

    echo "=== Upgrade complete ==="
    echo "The web container will run any pending database migrations on startup."
    echo "Check logs: docker compose -f $compose_file logs -f web"
    exit 0
fi

# ─── Uninstall path (early exit) ─────────────────────────────────────

if [ "$UNINSTALL" = true ]; then
    echo "=== kanban-mcp Uninstall ==="
    echo
    removed=""

    # 1. Remove pipx package
    if command -v pipx &>/dev/null && pipx list 2>/dev/null | grep -q "kanban-mcp"; then
        echo "Removing kanban-mcp package..."
        pipx uninstall kanban-mcp
        removed="${removed}  - kanban-mcp pipx package\n"
    else
        echo "kanban-mcp pipx package not found (skipping)."
    fi

    # Warn if kanban-mcp is still on PATH (pip/source install)
    if command -v kanban-mcp &>/dev/null; then
        echo "Warning: kanban-mcp is still on PATH (likely a pip or source install)."
        echo "  Location: $(command -v kanban-mcp)"
        echo "  To remove: pip uninstall kanban-mcp"
    fi
    echo

    # 2. Docker cleanup
    compose_file="$CONFIG_DIR/docker/docker-compose.yml"
    if [ -f "$compose_file" ]; then
        if command -v docker &>/dev/null && docker compose version &>/dev/null 2>&1; then
            # Load .env so compose can resolve variables
            if [ -f "$CONFIG_DIR/.env" ]; then
                set -a
                # shellcheck source=/dev/null
                source "$CONFIG_DIR/.env"
                set +a
            fi

            echo "Stopping Docker containers..."
            docker compose -f "$compose_file" down
            removed="${removed}  - Docker containers\n"

            if [ "$AUTO" = false ]; then
                echo
                read -rp "Remove Docker data volume? This DELETES ALL kanban data. [y/N] " REMOVE_VOLUME < /dev/tty
                REMOVE_VOLUME=${REMOVE_VOLUME:-N}
                if [[ "$REMOVE_VOLUME" =~ ^[Yy] ]]; then
                    docker compose -f "$compose_file" down -v
                    removed="${removed}  - Docker data volume\n"
                fi
            fi
        else
            echo "Docker not available — skipping container cleanup."
            echo "Docker files remain at: $CONFIG_DIR/docker/"
        fi
    fi
    echo

    # 3. MySQL database cleanup
    if [ "$AUTO" = false ]; then
        read -rp "Drop MySQL database and user? [y/N] " DROP_DB < /dev/tty
        DROP_DB=${DROP_DB:-N}
        if [[ "$DROP_DB" =~ ^[Yy] ]]; then
            # Read DB name/user from .env if available
            db_name="${KANBAN_DB_NAME:-kanban}"
            db_user="${KANBAN_DB_USER:-kanban}"
            db_host="${KANBAN_DB_HOST:-localhost}"

            if [ -f "$CONFIG_DIR/.env" ]; then
                # Source again in case not already loaded
                set -a
                # shellcheck source=/dev/null
                source "$CONFIG_DIR/.env"
                set +a
                db_name="${KANBAN_DB_NAME:-$db_name}"
                db_user="${KANBAN_DB_USER:-$db_user}"
                db_host="${KANBAN_DB_HOST:-$db_host}"
            fi

            echo "Will drop database '$db_name' and user '$db_user' on '$db_host'."
            read -rp "MySQL admin user [root]: " MYSQL_ADMIN < /dev/tty
            MYSQL_ADMIN=${MYSQL_ADMIN:-root}
            read -rsp "MySQL admin password: " MYSQL_ADMIN_PW < /dev/tty
            echo

            if command -v mysql &>/dev/null; then
                mysql -h "$db_host" -u "$MYSQL_ADMIN" -p"$MYSQL_ADMIN_PW" -e \
                    "DROP DATABASE IF EXISTS \`$db_name\`; DROP USER IF EXISTS '$db_user'@'%'; DROP USER IF EXISTS '$db_user'@'localhost'; FLUSH PRIVILEGES;" 2>/dev/null \
                    && removed="${removed}  - MySQL database '$db_name' and user '$db_user'\n" \
                    || echo "Warning: Failed to drop database/user. You may need to do this manually."
            else
                echo "mysql client not found. Drop manually:"
                echo "  DROP DATABASE IF EXISTS \`$db_name\`;"
                echo "  DROP USER IF EXISTS '$db_user'@'localhost';"
            fi
        fi
    fi
    echo

    # 4. Remove config directory
    if [ -d "$CONFIG_DIR" ]; then
        echo "Removing config directory: $CONFIG_DIR"
        rm -rf "$CONFIG_DIR"
        removed="${removed}  - Config directory ($CONFIG_DIR)\n"
    fi

    echo
    echo "=== Uninstall complete ==="
    if [ -n "$removed" ]; then
        echo
        echo "Removed:"
        echo -e "$removed"
    fi
    echo "You may also want to remove kanban-mcp from your MCP client config."
    exit 0
fi

# ─── Helper functions ───────────────────────────────────────────────

check_python() {
    if command -v python3 &>/dev/null; then
        PYTHON=python3
    elif command -v python &>/dev/null; then
        PYTHON=python
    else
        echo "Error: Python 3.10+ is required but not found."
        echo "Install Python from https://www.python.org/downloads/"
        exit 1
    fi

    local ver
    ver=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    local major minor
    major=$(echo "$ver" | cut -d. -f1)
    minor=$(echo "$ver" | cut -d. -f2)
    if [ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 10 ]; }; then
        echo "Error: Python 3.10+ is required (found $ver)."
        exit 1
    fi
    echo "Found Python $ver"
}

check_pipx() {
    if command -v pipx &>/dev/null; then
        echo "Found pipx"
        return 0
    fi
    return 1
}

install_pipx() {
    if command -v pipx &>/dev/null; then
        echo "Found pipx"
        return 0
    fi
    echo "Installing pipx..."
    $PYTHON -m pip install --user pipx 2>/dev/null || $PYTHON -m pip install pipx 2>/dev/null || {
        echo "Error: Could not install pipx. Install it manually:"
        echo "  https://pipx.pypa.io/stable/installation/"
        exit 1
    }
    $PYTHON -m pipx ensurepath 2>/dev/null || pipx ensurepath 2>/dev/null || true
    if ! command -v pipx &>/dev/null; then
        echo "pipx installed but not in PATH. You may need to restart your shell."
        echo "Continuing with: $PYTHON -m pipx"
    fi
}

install_kanban_mcp() {
    # Build extras string based on backend + semantic flags
    local extras=""
    if [ "$BACKEND" = "mysql" ]; then extras="mysql"; fi
    if [ "$WITH_SEMANTIC" = true ]; then
        if [ -n "$extras" ]; then extras="${extras},semantic"
        else extras="semantic"; fi
    fi
    local pkg="kanban-mcp"
    if [ -n "$extras" ]; then pkg="kanban-mcp[${extras}]"; fi

    # If run from a checkout with pyproject.toml, install from local
    # source instead of PyPI (ensures code and migrations match).
    if [ -f "pyproject.toml" ] && grep -q 'name = "kanban-mcp"' pyproject.toml 2>/dev/null; then
        local src="."
        if [ -n "$extras" ]; then src=".[${extras}]"; fi
        echo "Installing $pkg from local checkout via pipx..."
        if command -v pipx &>/dev/null; then
            pipx install "$src"
        else
            $PYTHON -m pipx install "$src"
        fi
    else
        echo "Installing $pkg via pipx..."
        if command -v pipx &>/dev/null; then
            pipx install "$pkg"
        else
            $PYTHON -m pipx install "$pkg"
        fi
    fi
    echo "kanban-mcp installed."
}

check_mysql_running() {
    local host="${1:-localhost}"
    local port="${2:-3306}"
    # Try TCP connection first (most reliable, no auth needed)
    # /dev/tcp is a bash builtin — works without external tools
    (echo >/dev/tcp/"$host"/"$port") &>/dev/null && return 0
    if command -v nc &>/dev/null; then
        nc -z -w2 "$host" "$port" &>/dev/null && return 0
    fi
    # Fall back to MySQL/MariaDB tools (may fail on auth, but ping
    # succeeds even without credentials on most configurations)
    if command -v mysqladmin &>/dev/null; then
        mysqladmin ping -h "$host" -P "$port" --connect-timeout=2 &>/dev/null && return 0
    fi
    if command -v mariadb-admin &>/dev/null; then
        mariadb-admin ping -h "$host" -P "$port" --connect-timeout=2 &>/dev/null && return 0
    fi
    return 1
}

check_docker() {
    command -v docker &>/dev/null && docker compose version &>/dev/null
}

start_docker_mysql() {
    local docker_dir="$CONFIG_DIR/docker"

    echo "Starting MySQL via Docker Compose..."
    docker compose -f "$docker_dir/docker-compose.yml" up -d

    echo "Waiting for MySQL to become healthy..."
    local retries=30
    while [ $retries -gt 0 ]; do
        if docker compose -f "$docker_dir/docker-compose.yml" ps --format json 2>/dev/null | grep -q '"healthy"'; then
            echo "MySQL is ready."
            return 0
        fi
        # Fallback check for older docker compose versions
        if docker compose -f "$docker_dir/docker-compose.yml" ps 2>/dev/null | grep -q "(healthy)"; then
            echo "MySQL is ready."
            return 0
        fi
        retries=$((retries - 1))
        sleep 2
    done

    echo "Warning: MySQL healthcheck timed out. It may still be starting."
    echo "Check status with: docker compose -f $docker_dir/docker-compose.yml ps"
}

run_db_setup() {
    local db_host="$1" db_name="$2" db_user="$3" db_password="$4" db_port="${5:-3306}"

    echo "--- Running kanban-setup ---"

    KANBAN_DB_HOST="$db_host" \
    KANBAN_DB_NAME="$db_name" \
    KANBAN_DB_USER="$db_user" \
    KANBAN_DB_PASSWORD="$db_password" \
    KANBAN_DB_PORT="$db_port" \
    MYSQL_ROOT_USER="${MYSQL_ROOT_USER:-root}" \
    MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-}" \
    kanban-setup --auto
}

write_env() {
    local db_host="$1" db_user="$2" db_password="$3" db_name="$4" db_port="${5:-3306}"

    mkdir -p "$CONFIG_DIR"
    local env_file="$CONFIG_DIR/.env"
    local write_it=true

    if [ -f "$env_file" ]; then
        if [ "$AUTO" = true ]; then
            true  # overwrite silently
        else
            read -rp "$env_file already exists. Overwrite? [y/N] " OVERWRITE < /dev/tty
            OVERWRITE=${OVERWRITE:-N}
            if [[ ! "$OVERWRITE" =~ ^[Yy] ]]; then
                echo "Skipping .env generation."
                write_it=false
            fi
        fi
    fi

    if [ "$write_it" = true ]; then
        cat > "$env_file" <<EOF
# kanban-mcp database configuration
KANBAN_DB_HOST=$db_host
KANBAN_DB_USER=$db_user
KANBAN_DB_PASSWORD=$db_password
KANBAN_DB_NAME=$db_name
EOF
        if [ "$db_port" != "3306" ]; then
            echo "KANBAN_DB_PORT=$db_port" >> "$env_file"
        fi
        echo "Created $env_file"
    fi
}

print_next_steps() {
    local backend="$1"
    shift

    echo
    echo "=== Setup complete ==="
    echo
    echo "Next steps:"
    echo
    echo "1. Add kanban-mcp to your MCP client config."
    echo

    if [ "$backend" = "sqlite" ]; then
        echo "   Claude Desktop (~/.config/Claude/claude_desktop_config.json):"
        echo '   {'
        echo '     "mcpServers": {'
        echo '       "kanban": {'
        echo '         "command": "kanban-mcp"'
        echo '       }'
        echo '     }'
        echo '   }'
    else
        local db_host="$1" db_user="$2" db_password="$3" db_name="$4"
        local is_docker="${5:-false}"
        echo "   Claude Desktop (~/.config/Claude/claude_desktop_config.json):"
        echo '   {'
        echo '     "mcpServers": {'
        echo '       "kanban": {'
        echo '         "command": "kanban-mcp",'
        echo '         "env": {'
        echo "           \"KANBAN_DB_HOST\": \"$db_host\","
        echo "           \"KANBAN_DB_USER\": \"$db_user\","
        echo "           \"KANBAN_DB_PASSWORD\": \"$db_password\","
        echo "           \"KANBAN_DB_NAME\": \"$db_name\""
        echo '         }'
        echo '       }'
        echo '     }'
        echo '   }'
    fi
    echo

    if [ "$backend" = "mysql" ] && [ "${is_docker:-false}" = true ]; then
        echo "2. The web UI is running at http://localhost:5000"
    else
        echo "2. Start the web UI (optional):"
        echo "   kanban-web"
        echo "   Open http://localhost:5000"
    fi
    echo
    echo "3. Verify installation:"
    echo "   kanban-cli --project /path/to/your/project summary"
    echo

    # Print hook config snippet if hook commands are found
    local hook_start hook_stop
    hook_start=$(command -v kanban-hook-session-start 2>/dev/null || true)
    hook_stop=$(command -v kanban-hook-stop 2>/dev/null || true)
    if [ -n "$hook_start" ] && [ -n "$hook_stop" ]; then
        echo "4. Set up hooks (recommended for Claude Code):"
        echo
        echo "   Hooks inject active kanban items at session start and"
        echo "   prompt for progress updates when the session ends."
        echo "   Without hooks, the agent only uses the board when asked."
        echo
        echo "   Merge into ~/.claude/settings.json:"
        echo
        echo '   {'
        echo '     "hooks": {'
        echo '       "SessionStart": ['
        echo '         { "hooks": [{ "type": "command", "command": "'"$hook_start"'" }] }'
        echo '       ],'
        echo '       "Stop": ['
        echo '         { "hooks": [{ "type": "command", "command": "'"$hook_stop"'" }] }'
        echo '       ]'
        echo '     }'
        echo '   }'
        echo
        echo "   If you already have hooks configured, add the entries to"
        echo "   the existing SessionStart and Stop arrays."
        echo
    fi
}

# ─── Step 1: Python & backend selection ─────────────────────────────

check_python

echo

# Determine backend before installing so we pick the right extras
BACKEND=""       # "sqlite" or "mysql"
MYSQL_METHOD=""  # "local", "remote", or "docker" (only when BACKEND=mysql)

if [ "$USE_DOCKER" = true ] || [ -n "$DB_HOST_ARG" ] || [ "$USE_MYSQL" = true ]; then
    BACKEND="mysql"
elif [ -n "${KANBAN_DB_USER:-}" ] && [ -n "${KANBAN_DB_PASSWORD:-}" ] && [ -n "${KANBAN_DB_NAME:-}" ]; then
    BACKEND="mysql"
elif [ "$AUTO" = true ]; then
    BACKEND="sqlite"
else
    # Interactive: ask for backend
    echo "Choose your database backend:"
    echo "  1) SQLite (recommended, zero config)"
    echo "  2) MySQL/MariaDB (local)"
    echo "  3) MySQL/MariaDB (remote)"
    echo "  4) MySQL via Docker"
    read -rp "Choice [1]: " BACKEND_CHOICE < /dev/tty
    BACKEND_CHOICE=${BACKEND_CHOICE:-1}

    case "$BACKEND_CHOICE" in
        1) BACKEND="sqlite" ;;
        2) BACKEND="mysql"; MYSQL_METHOD="local" ;;
        3) BACKEND="mysql"; MYSQL_METHOD="remote" ;;
        4) BACKEND="mysql"; MYSQL_METHOD="docker" ;;
        *)
            echo "Invalid choice. Using SQLite."
            BACKEND="sqlite"
            ;;
    esac
fi

# For MySQL backend, determine connection method if not set above
if [ "$BACKEND" = "mysql" ] && [ -z "$MYSQL_METHOD" ]; then
    if [ "$USE_DOCKER" = true ]; then
        MYSQL_METHOD="docker"
    elif [ -n "$DB_HOST_ARG" ]; then
        MYSQL_METHOD="remote"
        DB_HOST="$DB_HOST_ARG"
    else
        MYSQL_METHOD="local"
    fi
fi

if [ "$BACKEND" = "mysql" ]; then
    case "$MYSQL_METHOD" in
        local)
            DB_HOST="${KANBAN_DB_HOST:-localhost}"
            local_port="${KANBAN_DB_PORT:-3306}"
            if [ "$AUTO" != true ]; then
                read -rp "MySQL/MariaDB port [$local_port]: " DB_PORT_INPUT < /dev/tty
                local_port=${DB_PORT_INPUT:-$local_port}
            fi
            if check_mysql_running "$DB_HOST" "$local_port"; then
                echo "MySQL/MariaDB is running on $DB_HOST:$local_port."
            else
                echo "MySQL/MariaDB is not running on $DB_HOST."
                if check_docker; then
                    if [ "$AUTO" = true ]; then
                        echo "Use --docker flag to start MySQL via Docker."
                        echo "Or start MySQL manually and re-run this script."
                        exit 1
                    fi
                    read -rp "Start MySQL via Docker? [Y/n] " START_DOCKER < /dev/tty
                    START_DOCKER=${START_DOCKER:-Y}
                    if [[ "$START_DOCKER" =~ ^[Yy] ]]; then
                        MYSQL_METHOD="docker"
                    else
                        echo
                        echo "Please start MySQL/MariaDB and re-run this script."
                        echo "  Ubuntu/Debian: sudo systemctl start mysql"
                        echo "  macOS:         brew services start mysql"
                        echo "  Arch/Fedora:   sudo systemctl start mariadb"
                        exit 1
                    fi
                else
                    echo
                    echo "Docker is not available either. Please install MySQL/MariaDB or Docker:"
                    echo "  MySQL:   https://dev.mysql.com/downloads/"
                    echo "  MariaDB: https://mariadb.org/download/"
                    echo "  Docker:  https://docs.docker.com/get-docker/"
                    exit 1
                fi
            fi
            ;;

        remote)
            if [ -z "$DB_HOST" ]; then
                read -rp "MySQL host: " DB_HOST < /dev/tty
            fi
            if [ -z "$DB_HOST" ]; then
                echo "Error: No host provided."
                exit 1
            fi
            local_port="3306"
            if [ "$AUTO" = false ]; then
                read -rp "MySQL port [$local_port]: " DB_PORT_INPUT < /dev/tty
                local_port=${DB_PORT_INPUT:-$local_port}
            fi
            echo "Will connect to MySQL at $DB_HOST:$local_port"
            ;;

        docker)
            if ! check_docker; then
                echo "Error: Docker is not installed or docker compose is not available."
                echo "Install Docker: https://docs.docker.com/get-docker/"
                exit 1
            fi
            ;;
    esac
fi

echo

# ─── Step 2: Install kanban-mcp ────────────────────────────────────

if ! command -v kanban-mcp &>/dev/null; then
    if [ "$AUTO" = true ]; then
        # Auto mode: install without asking
        if ! check_pipx; then
            install_pipx
        fi
        install_kanban_mcp
    else
        echo "kanban-mcp is not installed."
        read -rp "Install kanban-mcp via pipx? [Y/n] " INSTALL_IT < /dev/tty
        INSTALL_IT=${INSTALL_IT:-Y}
        if [[ "$INSTALL_IT" =~ ^[Yy] ]]; then
            if ! check_pipx; then
                install_pipx
            fi
            install_kanban_mcp
        else
            echo "Skipping kanban-mcp install. You can install manually with: pipx install kanban-mcp"
        fi
    fi
else
    echo "Found kanban-mcp"
fi

echo

# ─── Step 3: Execute the chosen path ────────────────────────────────

if [ "$BACKEND" = "sqlite" ]; then
    # SQLite path: zero config, just run setup + migrations
    echo "Setting up SQLite backend..."
    kanban-setup --auto --backend sqlite
    print_next_steps "sqlite"

elif [ "$MYSQL_METHOD" = "docker" ]; then
    # Docker path: download files, start compose, use compose defaults
    DB_NAME="${KANBAN_DB_NAME:-kanban}"
    DB_USER="${KANBAN_DB_USER:-kanban}"
    DB_PASSWORD="${KANBAN_DB_PASSWORD:-changeme}"
    DB_HOST="localhost"
    local_port="${KANBAN_DB_PORT:-3306}"

    # Check for port conflict before starting Docker MySQL
    if check_mysql_running "$DB_HOST" "$local_port"; then
        echo "Warning: Port $local_port is already in use on $DB_HOST."
        if [ "$AUTO" = true ]; then
            echo "Set KANBAN_DB_PORT to use a different port."
            exit 1
        fi
        alt_port=$((local_port + 1))
        read -rp "Use alternative port $alt_port instead? [Y/n] " USE_ALT < /dev/tty
        USE_ALT=${USE_ALT:-Y}
        if [[ "$USE_ALT" =~ ^[Yy] ]]; then
            local_port="$alt_port"
            echo "Using port $local_port."
        else
            read -rp "Enter port number: " CUSTOM_PORT < /dev/tty
            if [ -z "$CUSTOM_PORT" ]; then
                echo "No port specified. Aborting."
                exit 1
            fi
            local_port="$CUSTOM_PORT"
            echo "Using port $local_port."
        fi
    fi
    export KANBAN_DB_PORT="$local_port"

    download_docker_files
    echo

    # Export env vars so docker-compose.yml picks them up
    export KANBAN_DB_NAME="$DB_NAME"
    export KANBAN_DB_USER="$DB_USER"
    export KANBAN_DB_PASSWORD="$DB_PASSWORD"

    start_docker_mysql
    echo

    # Write .env and print instructions
    write_env "$DB_HOST" "$DB_USER" "$DB_PASSWORD" "$DB_NAME" "$local_port"
    print_next_steps "mysql" "$DB_HOST" "$DB_USER" "$DB_PASSWORD" "$DB_NAME" true

    echo "Docker compose files: $CONFIG_DIR/docker/"
    echo "Manage with: docker compose -f $CONFIG_DIR/docker/docker-compose.yml [up|down|logs]"
    echo

else
    # Local or remote MySQL: gather creds and run DB setup

    if [ "$AUTO" = true ]; then
        DB_NAME="${KANBAN_DB_NAME:-kanban}"
        DB_USER="${KANBAN_DB_USER:-kanban}"
        DB_HOST="${DB_HOST:-${KANBAN_DB_HOST:-localhost}}"

        if [ -z "${KANBAN_DB_PASSWORD:-}" ]; then
            DB_PASSWORD=$($PYTHON -c "import secrets; print(secrets.token_urlsafe(16))" 2>/dev/null || openssl rand -base64 16)
            echo "Generated password: $DB_PASSWORD"
        else
            DB_PASSWORD="$KANBAN_DB_PASSWORD"
        fi
    else
        read -rp "Database name [kanban]: " DB_NAME < /dev/tty
        DB_NAME=${DB_NAME:-kanban}

        read -rp "Database user [kanban]: " DB_USER < /dev/tty
        DB_USER=${DB_USER:-kanban}

        read -rsp "Database password (leave blank to auto-generate): " DB_PASSWORD < /dev/tty
        echo
        if [ -z "$DB_PASSWORD" ]; then
            DB_PASSWORD=$($PYTHON -c "import secrets; print(secrets.token_urlsafe(16))" 2>/dev/null || openssl rand -base64 16)
            echo "Generated password: $DB_PASSWORD"
        fi

        if [ "$MYSQL_METHOD" = "local" ]; then
            DB_HOST="${DB_HOST:-localhost}"
        else
            # Remote — already set from earlier prompt
            true
        fi

        read -rp "MySQL root user for setup [root]: " MYSQL_ROOT_USER_INPUT < /dev/tty
        MYSQL_ROOT_USER=${MYSQL_ROOT_USER_INPUT:-${MYSQL_ROOT_USER:-root}}

        read -rsp "MySQL root password (blank for socket auth): " MYSQL_ROOT_PASSWORD_INPUT < /dev/tty
        echo
        MYSQL_ROOT_PASSWORD=${MYSQL_ROOT_PASSWORD_INPUT:-${MYSQL_ROOT_PASSWORD:-}}
    fi

    echo
    echo "Configuration:"
    echo "  Database: $DB_NAME"
    echo "  User:     $DB_USER"
    echo "  Host:     $DB_HOST"
    echo

    if [ "$AUTO" = false ]; then
        read -rp "Proceed? [Y/n] " CONFIRM < /dev/tty
        CONFIRM=${CONFIRM:-Y}
        if [[ ! "$CONFIRM" =~ ^[Yy] ]]; then
            echo "Aborted."
            exit 0
        fi
    fi

    run_db_setup "$DB_HOST" "$DB_NAME" "$DB_USER" "$DB_PASSWORD" "${local_port:-3306}"

    write_env "$DB_HOST" "$DB_USER" "$DB_PASSWORD" "$DB_NAME" "${local_port:-3306}"
    print_next_steps "mysql" "$DB_HOST" "$DB_USER" "$DB_PASSWORD" "$DB_NAME"
fi
