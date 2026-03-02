#!/bin/bash
#
# kanban-mcp database setup script
# Sets up MySQL database, user, and runs migrations.
# Requires: mysql client, MySQL 8.0+ server running
#
# Interactive (default):
#   ./install.sh
#
# Non-interactive (for AI agents / automation):
#   ./install.sh --auto
#   Uses env vars or defaults: KANBAN_DB_NAME, KANBAN_DB_USER,
#   KANBAN_DB_PASSWORD (auto-generated if unset), KANBAN_DB_HOST,
#   MYSQL_ROOT_USER, MYSQL_ROOT_PASSWORD
#
# Options:
#   --auto            Non-interactive mode (no prompts)
#   --with-semantic   Also install semantic search dependencies
#

set -euo pipefail

AUTO=false
WITH_SEMANTIC=false

for arg in "$@"; do
    case "$arg" in
        --auto) AUTO=true ;;
        --with-semantic) WITH_SEMANTIC=true ;;
        --help|-h)
            echo "Usage: ./install.sh [--auto] [--with-semantic]"
            echo ""
            echo "Options:"
            echo "  --auto            Non-interactive mode (uses env vars or defaults)"
            echo "  --with-semantic   Also install semantic search dependencies"
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

echo "=== kanban-mcp Database Setup ==="
echo

# Check mysql client is available
if ! command -v mysql &>/dev/null; then
    echo "Error: mysql client not found. Install it first:"
    echo "  Ubuntu/Debian: sudo apt install mysql-client"
    echo "  macOS:         brew install mysql-client"
    echo "  Arch:          sudo pacman -S mariadb-clients"
    exit 1
fi

# Find migration files
MIGRATIONS_DIR=""
if [ -d "./kanban_mcp/migrations" ]; then
    MIGRATIONS_DIR="./kanban_mcp/migrations"
else
    # Try to find from pip-installed package
    PACKAGE_DIR=$(python3 -c "import kanban_mcp; import os; print(os.path.dirname(kanban_mcp.__file__))" 2>/dev/null || true)
    if [ -n "$PACKAGE_DIR" ] && [ -d "$PACKAGE_DIR/migrations" ]; then
        MIGRATIONS_DIR="$PACKAGE_DIR/migrations"
    fi
fi

if [ -z "$MIGRATIONS_DIR" ]; then
    echo "Error: Could not find migration files."
    echo "Run this script from the kanban-mcp repo root, or ensure kanban-mcp is pip-installed."
    exit 1
fi

echo "Found migrations in: $MIGRATIONS_DIR"
echo

# --- Gather configuration ---

if [ "$AUTO" = true ]; then
    # Non-interactive: use env vars with defaults
    DB_NAME="${KANBAN_DB_NAME:-kanban}"
    DB_USER="${KANBAN_DB_USER:-kanban}"
    DB_HOST="${KANBAN_DB_HOST:-localhost}"
    MYSQL_ROOT_USER="${MYSQL_ROOT_USER:-root}"

    if [ -z "${KANBAN_DB_PASSWORD:-}" ]; then
        DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))" 2>/dev/null || openssl rand -base64 16)
        echo "Generated password: $DB_PASSWORD"
    else
        DB_PASSWORD="$KANBAN_DB_PASSWORD"
    fi
else
    # Interactive: prompt user
    read -rp "Database name [kanban]: " DB_NAME
    DB_NAME=${DB_NAME:-kanban}

    read -rp "Database user [kanban]: " DB_USER
    DB_USER=${DB_USER:-kanban}

    read -rp "Database password (leave blank to auto-generate): " DB_PASSWORD
    if [ -z "$DB_PASSWORD" ]; then
        DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))" 2>/dev/null || openssl rand -base64 16)
        echo "Generated password: $DB_PASSWORD"
    fi

    read -rp "Database host [localhost]: " DB_HOST
    DB_HOST=${DB_HOST:-localhost}

    read -rp "MySQL root user for setup [root]: " MYSQL_ROOT_USER
    MYSQL_ROOT_USER=${MYSQL_ROOT_USER:-root}
fi

echo
echo "Configuration:"
echo "  Database: $DB_NAME"
echo "  User:     $DB_USER"
echo "  Host:     $DB_HOST"
echo

if [ "$AUTO" = false ]; then
    read -rp "Proceed? [Y/n] " CONFIRM
    CONFIRM=${CONFIRM:-Y}
    if [[ ! "$CONFIRM" =~ ^[Yy] ]]; then
        echo "Aborted."
        exit 0
    fi
fi

# --- Create database and user ---

echo "--- Creating database and user ---"

MYSQL_AUTH=(-u "$MYSQL_ROOT_USER" -h "$DB_HOST")
if [ -n "${MYSQL_ROOT_PASSWORD:-}" ]; then
    MYSQL_AUTH+=(-p"$MYSQL_ROOT_PASSWORD")
elif [ "$AUTO" = false ]; then
    echo "(You may be prompted for the MySQL root password)"
    MYSQL_AUTH+=(-p)
else
    # Auto mode without root password — try without password (e.g. socket auth)
    true
fi

mysql "${MYSQL_AUTH[@]}" <<EOF
CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '$DB_USER'@'%' IDENTIFIED BY '$DB_PASSWORD';
GRANT ALL PRIVILEGES ON \`$DB_NAME\`.* TO '$DB_USER'@'%';
FLUSH PRIVILEGES;
EOF

echo "Database and user created."

# --- Run migrations ---

echo
echo "--- Running migrations ---"

for migration in "$MIGRATIONS_DIR"/0*.sql; do
    echo "  Applying $(basename "$migration")..."
    mysql -u "$DB_USER" -p"$DB_PASSWORD" -h "$DB_HOST" "$DB_NAME" < "$migration"
done

echo "Migrations complete."

# --- Install semantic dependencies ---

if [ "$WITH_SEMANTIC" = true ]; then
    echo
    echo "--- Installing semantic search dependencies ---"
    pip install "kanban-mcp[semantic]"
    echo "Semantic search dependencies installed."
fi

# --- Generate .env file ---

ENV_FILE=".env"
WRITE_ENV=true

if [ -f "$ENV_FILE" ]; then
    if [ "$AUTO" = true ]; then
        # Auto mode: overwrite silently
        true
    else
        read -rp ".env file already exists. Overwrite? [y/N] " OVERWRITE
        OVERWRITE=${OVERWRITE:-N}
        if [[ ! "$OVERWRITE" =~ ^[Yy] ]]; then
            echo "Skipping .env generation."
            WRITE_ENV=false
        fi
    fi
fi

if [ "$WRITE_ENV" = true ]; then
    cat > "$ENV_FILE" <<EOF
# kanban-mcp database configuration
KANBAN_DB_HOST=$DB_HOST
KANBAN_DB_USER=$DB_USER
KANBAN_DB_PASSWORD=$DB_PASSWORD
KANBAN_DB_NAME=$DB_NAME
EOF
    echo "Created $ENV_FILE"
fi

echo
echo "=== Setup complete ==="
echo
echo "Next steps:"
echo
echo "1. Add kanban-mcp to your MCP client config."
echo
echo "   Claude Desktop (~/.config/Claude/claude_desktop_config.json):"
echo '   {'
echo '     "mcpServers": {'
echo '       "kanban": {'
echo '         "command": "kanban-mcp",'
echo '         "env": {'
echo "           \"KANBAN_DB_HOST\": \"$DB_HOST\","
echo "           \"KANBAN_DB_USER\": \"$DB_USER\","
echo "           \"KANBAN_DB_PASSWORD\": \"$DB_PASSWORD\","
echo "           \"KANBAN_DB_NAME\": \"$DB_NAME\""
echo '         }'
echo '       }'
echo '     }'
echo '   }'
echo
echo "2. Start the web UI (optional):"
echo "   kanban-web"
echo "   Open http://localhost:5000"
echo
echo "3. Verify installation:"
echo "   kanban-cli --project /path/to/your/project summary"
echo
