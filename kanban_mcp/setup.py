#!/usr/bin/env python3
"""
kanban-setup: Cross-platform database setup for kanban-mcp.

Replaces install.sh / install.ps1 as the primary DB setup mechanism
for pip-installed users. Two modes:

  Interactive (default):  kanban-setup
  Non-interactive:        kanban-setup --auto
"""

import argparse
import json
import logging
import os
import secrets
import subprocess
import sys
from pathlib import Path

import mysql.connector
from mysql.connector import Error as MySQLError

# Migrations numbered <= this are backfilled for pre-versioning installs
_BACKFILL_CUTOFF = 4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kanban-setup",
        description="Set up the MySQL database for kanban-mcp",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Non-interactive mode (uses env vars, CLI args, or defaults)",
    )
    parser.add_argument(
        "--with-semantic",
        action="store_true",
        help=(
            "Also install semantic search dependencies"
            " (numpy, onnxruntime, etc.)"
        ),
    )
    parser.add_argument(
        "--db-name", default=None, help="Database name",
    )
    parser.add_argument(
        "--db-user", default=None, help="Database user",
    )
    parser.add_argument(
        "--db-password", default=None, help="Database password",
    )
    parser.add_argument(
        "--db-host", default=None, help="MySQL host",
    )
    parser.add_argument(
        "--mysql-root-user", default=None,
        help="MySQL admin user for setup",
    )
    parser.add_argument(
        "--mysql-root-password", default=None,
        help="MySQL admin password",
    )
    parser.add_argument(
        "--migrate-only",
        action="store_true",
        help=(
            "Only run migrations (skip DB/user creation"
            " and .env writing). Useful for upgrades."
        ),
    )
    return parser


def generate_password() -> str:
    """Generate a secure random password."""
    return secrets.token_urlsafe(16)


def find_migrations_dir() -> str | None:
    """Find the migrations directory.

    Checks two locations:
    1. Local repo: ./kanban_mcp/migrations (when run from repo root)
    2. Package install: alongside this file at kanban_mcp/migrations
    """
    # Local repo check
    local = Path.cwd() / "kanban_mcp" / "migrations"
    if local.is_dir() and list(local.glob("0*.sql")):
        return str(local)

    # Package install check
    package = Path(__file__).parent / "migrations"
    if package.is_dir() and list(package.glob("0*.sql")):
        return str(package)

    return None


def get_migration_files() -> list[Path]:
    """Return sorted list of migration SQL files."""
    migrations_dir = find_migrations_dir()
    if migrations_dir is None:
        return []
    return sorted(Path(migrations_dir).glob("0*.sql"))


def write_env_file(
    path: str,
    db_host: str,
    db_user: str,
    db_password: str,
    db_name: str,
) -> None:
    """Write a .env file with kanban-mcp database configuration."""
    content = (
        "# kanban-mcp database configuration\n"
        f"KANBAN_DB_HOST={db_host}\n"
        f"KANBAN_DB_USER={db_user}\n"
        f"KANBAN_DB_PASSWORD={db_password}\n"
        f"KANBAN_DB_NAME={db_name}\n"
    )
    Path(path).write_text(content)


def resolve_config(args: argparse.Namespace) -> dict:
    """Resolve configuration from CLI args > env vars > defaults.

    In auto mode, values come from CLI args first, then env vars,
    then defaults. In interactive mode, this provides defaults for
    the prompts.
    """
    def _resolve(cli_val, env_key, default):
        if cli_val is not None:
            return cli_val
        env_val = os.environ.get(env_key)
        if env_val:
            return env_val
        return default

    db_password = _resolve(
        args.db_password, "KANBAN_DB_PASSWORD", None,
    )
    if db_password is None and args.auto:
        db_password = generate_password()

    return {
        "db_name": _resolve(
            args.db_name, "KANBAN_DB_NAME", "kanban",
        ),
        "db_user": _resolve(
            args.db_user, "KANBAN_DB_USER", "kanban",
        ),
        "db_password": db_password,
        "db_host": _resolve(
            args.db_host, "KANBAN_DB_HOST", "localhost",
        ),
        "mysql_root_user": _resolve(
            args.mysql_root_user, "MYSQL_ROOT_USER", "root",
        ),
        "mysql_root_password": _resolve(
            args.mysql_root_password,
            "MYSQL_ROOT_PASSWORD",
            None,
        ),
    }


def mcp_config_json(
    db_host: str, db_user: str, db_password: str, db_name: str,
) -> str:
    """Return MCP config JSON string with explicit credentials."""
    config = {
        "mcpServers": {
            "kanban": {
                "command": "kanban-mcp",
                "env": {
                    "KANBAN_DB_HOST": db_host,
                    "KANBAN_DB_USER": db_user,
                    "KANBAN_DB_PASSWORD": db_password,
                    "KANBAN_DB_NAME": db_name,
                },
            }
        }
    }
    return json.dumps(config, indent=2)


def mcp_config_minimal_json() -> str:
    """Return minimal MCP config (credentials read from .env)."""
    config = {
        "mcpServers": {
            "kanban": {
                "command": "kanban-mcp",
            }
        }
    }
    return json.dumps(config, indent=2)


def _prompt(message: str, default: str = "") -> str:
    """Prompt user for input with a default value."""
    if default:
        raw = input(f"{message} [{default}]: ").strip()
        return raw if raw else default
    return input(f"{message}: ").strip()


def _run_interactive(args: argparse.Namespace) -> dict:
    """Gather configuration interactively."""
    defaults = resolve_config(args)

    db_name = _prompt(
        "Database name", defaults["db_name"] or "kanban",
    )
    db_user = _prompt(
        "Database user", defaults["db_user"] or "kanban",
    )

    db_password = _prompt(
        "Database password (leave blank to auto-generate)", "",
    )
    if not db_password:
        db_password = generate_password()
        print(f"Generated password: {db_password}")

    db_host = _prompt(
        "Database host", defaults["db_host"] or "localhost",
    )
    mysql_root_user = _prompt(
        "MySQL root user for setup",
        defaults["mysql_root_user"] or "root",
    )
    mysql_root_password = _prompt(
        "MySQL root password (blank for socket auth)", "",
    )

    return {
        "db_name": db_name,
        "db_user": db_user,
        "db_password": db_password,
        "db_host": db_host,
        "mysql_root_user": mysql_root_user,
        "mysql_root_password": mysql_root_password or None,
    }


def _find_mysql_socket() -> str | None:
    """Find the MySQL Unix socket path."""
    candidates = [
        "/var/run/mysqld/mysqld.sock",   # Debian/Ubuntu
        "/var/lib/mysql/mysql.sock",     # RHEL/CentOS
        "/tmp/mysql.sock",               # macOS (Homebrew)  # nosec B108
        "/var/mysql/mysql.sock",         # macOS (official)
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _create_database(config: dict) -> None:
    """Connect as MySQL root and create the database + user."""
    connect_args = {
        "user": config["mysql_root_user"],
        "host": config["db_host"],
    }
    if config["mysql_root_password"]:
        connect_args["password"] = config["mysql_root_password"]

    # On localhost without a password, try Unix socket auth
    # (Debian/Ubuntu default to auth_socket for root)
    if (
        config["db_host"] in ("localhost", "127.0.0.1")
        and not config["mysql_root_password"]
    ):
        sock = _find_mysql_socket()
        if sock:
            connect_args["unix_socket"] = sock
            # Remove host — socket and host are mutually exclusive
            connect_args.pop("host", None)

    print("Connecting to MySQL as root...")
    try:
        conn = mysql.connector.connect(**connect_args)
    except MySQLError as e:
        print(
            f"Error: Could not connect to MySQL"
            f" as {config['mysql_root_user']}: {e}"
        )
        sys.exit(1)

    cursor = conn.cursor()
    db = config["db_name"]
    user = config["db_user"]
    pw = config["db_password"]

    statements = [
        (
            f"CREATE DATABASE IF NOT EXISTS `{db}`"
            " CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        ),
        (
            f"CREATE USER IF NOT EXISTS '{user}'@'%'"
            f" IDENTIFIED BY '{pw}'"
        ),
        f"GRANT ALL PRIVILEGES ON `{db}`.* TO '{user}'@'%'",
        "FLUSH PRIVILEGES",
    ]

    for stmt in statements:
        cursor.execute(stmt)

    conn.commit()
    cursor.close()
    conn.close()
    print("Database and user created.")


def _split_sql(sql: str) -> list[str]:
    """Split a SQL script on semicolons, ignoring empty statements."""
    return [
        s.strip() for s in sql.split(";") if s.strip()
    ]


def _ensure_schema_migrations_table(cursor) -> None:
    """Create the schema_migrations tracking table if needed."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename VARCHAR(255) PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


def _get_applied_migrations(cursor) -> set[str]:
    """Return set of migration filenames already applied."""
    cursor.execute("SELECT filename FROM schema_migrations")
    return {row[0] for row in cursor.fetchall()}


def _backfill_existing_install(
    cursor, migration_files: list[Path],
) -> bool:
    """Detect pre-versioning installs and backfill records.

    Returns True if backfill was performed.
    """
    # Check if items table exists (sign of existing install)
    cursor.execute(
        "SELECT TABLE_NAME FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE()"
        " AND TABLE_NAME = 'items'"
    )
    if cursor.fetchone() is None:
        return False

    # Check if schema_migrations is empty
    cursor.execute("SELECT COUNT(*) FROM schema_migrations")
    count = cursor.fetchone()[0]
    if count > 0:
        return False

    # Backfill only migrations <= _BACKFILL_CUTOFF
    print(
        "  Detected existing install"
        " — backfilling migration records for 001-004..."
    )
    for mfile in migration_files:
        # Extract leading number from filename
        # e.g. "001" from "001_initial_schema.sql"
        num_str = mfile.name.split("_")[0]
        try:
            num = int(num_str)
        except ValueError:
            continue
        if num <= _BACKFILL_CUTOFF:
            cursor.execute(
                "INSERT IGNORE INTO schema_migrations"
                " (filename) VALUES (%s)",
                (mfile.name,),
            )
    return True


def _run_migrations(config: dict) -> None:
    """Connect as kanban user and run migrations with tracking."""
    migration_files = get_migration_files()
    if not migration_files:
        print("Error: Could not find migration files.")
        print(
            "Run this from the kanban-mcp repo root,"
            " or ensure kanban-mcp is pip-installed."
        )
        sys.exit(1)

    print(
        f"Found {len(migration_files)} migration(s)"
        f" in: {migration_files[0].parent}"
    )

    conn = mysql.connector.connect(
        user=config["db_user"],
        password=config["db_password"],
        host=config["db_host"],
        database=config["db_name"],
    )
    cursor = conn.cursor()

    # 1. Ensure tracking table exists
    _ensure_schema_migrations_table(cursor)
    conn.commit()

    # 2. Backfill for pre-versioning installs
    _backfill_existing_install(cursor, migration_files)
    conn.commit()

    # 3. Get already-applied set
    applied = _get_applied_migrations(cursor)

    # 4. Apply each unapplied migration
    applied_count = 0
    skipped_count = 0
    for mfile in migration_files:
        if mfile.name in applied:
            print(f"  Already applied: {mfile.name}")
            skipped_count += 1
            continue

        print(f"  Applying {mfile.name}...")
        sql = mfile.read_text()
        try:
            for stmt in _split_sql(sql):
                cursor.execute(stmt)
            cursor.execute(
                "INSERT INTO schema_migrations"
                " (filename) VALUES (%s)",
                (mfile.name,),
            )
            conn.commit()
            applied_count += 1
        except MySQLError as e:
            conn.rollback()
            print(f"  ERROR applying {mfile.name}: {e}")
            print(
                "  Aborting migrations."
                " Fix the issue and re-run."
            )
            cursor.close()
            conn.close()
            sys.exit(1)

    cursor.close()
    conn.close()
    print(
        f"Migrations complete."
        f" Applied: {applied_count},"
        f" already up-to-date: {skipped_count}."
    )


def auto_migrate(db_config: dict) -> None:
    """Run pending migrations at server startup.

    Unlike _run_migrations(), this function:
    - Takes a KanbanDB.config-shaped dict (host/user/password/database)
    - Logs instead of printing
    - Never calls sys.exit — errors are logged and swallowed
    - Is safe to call on every server start
    """
    log = logging.getLogger("kanban-mcp.migrate")

    migration_files = get_migration_files()
    if not migration_files:
        log.debug("No migration files found, skipping.")
        return

    try:
        conn = mysql.connector.connect(**db_config)
    except MySQLError as e:
        log.error("Auto-migrate: DB connect failed: %s", e)
        return

    try:
        cursor = conn.cursor()

        _ensure_schema_migrations_table(cursor)
        conn.commit()

        _backfill_existing_install(cursor, migration_files)
        conn.commit()

        applied = _get_applied_migrations(cursor)

        for mfile in migration_files:
            if mfile.name in applied:
                continue

            log.info("Applying migration: %s", mfile.name)
            sql = mfile.read_text()
            try:
                for stmt in _split_sql(sql):
                    cursor.execute(stmt)
                cursor.execute(
                    "INSERT INTO schema_migrations"
                    " (filename) VALUES (%s)",
                    (mfile.name,),
                )
                conn.commit()
            except MySQLError as e:
                conn.rollback()
                log.error(
                    "Migration %s failed: %s",
                    mfile.name, e,
                )
                break

        cursor.close()
    except MySQLError as e:
        log.error("Auto-migrate error: %s", e)
    finally:
        conn.close()


def _handle_env_file(config: dict, auto: bool) -> None:
    """Write .env file to the user config directory.

    Writes to ~/.config/kanban-mcp/.env (Linux/macOS) or
    %APPDATA%/kanban-mcp/.env (Windows). This is the same location
    that core.py loads from, so all install methods (pipx, pip,
    source) use a single consistent config path.
    """
    from kanban_mcp.core import get_config_dir

    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    env_path = str(config_dir / ".env")
    write = True

    if os.path.exists(env_path):
        if auto:
            pass  # overwrite silently
        else:
            overwrite = _prompt(
                f"{env_path} already exists. Overwrite? [y/N]",
                "N",
            )
            if not overwrite.lower().startswith("y"):
                print("Skipping .env generation.")
                write = False

    if write:
        write_env_file(
            env_path,
            db_host=config["db_host"],
            db_user=config["db_user"],
            db_password=config["db_password"],
            db_name=config["db_name"],
        )
        print(f"Created {env_path}")


def _install_semantic() -> None:
    """Install semantic search dependencies."""
    print("Installing semantic search dependencies...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "kanban-mcp[semantic]"],
    )
    print("Semantic search dependencies installed.")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    print("=== kanban-mcp Database Setup ===")
    print()

    # Gather config
    if args.auto:
        config = resolve_config(args)
        if config["db_password"] is None:
            config["db_password"] = generate_password()
            print(f"Generated password: {config['db_password']}")
    else:
        config = _run_interactive(args)

    print()
    print("Configuration:")
    print(f"  Database: {config['db_name']}")
    print(f"  User:     {config['db_user']}")
    print(f"  Host:     {config['db_host']}")
    print()

    if args.migrate_only:
        # --migrate-only: skip DB creation, .env, next-steps
        print("--- Running migrations (migrate-only mode) ---")
        _run_migrations(config)
        print()
        print("=== Migration complete ===")
        return

    if not args.auto:
        confirm = _prompt("Proceed? [Y/n]", "Y")
        if not confirm.lower().startswith("y"):
            print("Aborted.")
            return

    # Create database and user
    print("--- Creating database and user ---")
    _create_database(config)

    # Run migrations
    print()
    print("--- Running migrations ---")
    _run_migrations(config)

    # Install semantic if requested
    if args.with_semantic:
        print()
        print("--- Installing semantic search dependencies ---")
        _install_semantic()

    # Write .env
    print()
    _handle_env_file(config, args.auto)

    # Print next steps
    from kanban_mcp.core import get_config_dir
    env_path = get_config_dir() / ".env"

    print()
    print("=== Setup complete ===")
    print()
    print(f"Credentials saved to: {env_path}")
    print()
    print("Next steps:")
    print()
    print("1. Add kanban-mcp to your MCP client config.")
    print()
    print("   Since credentials are in .env, you just need:")
    print()
    print(mcp_config_minimal_json())
    print()
    print("   Add to the config file for your tool:")
    print()
    _print_tool_table()
    print()
    print("   If your tool can't read .env, pass creds:")
    print()
    print(mcp_config_json(
        config["db_host"],
        config["db_user"],
        config["db_password"],
        config["db_name"],
    ))
    print()
    print("2. Start the web UI (optional):")
    print("   kanban-web")
    print("   Open http://localhost:5000")
    print()
    print("3. Verify installation:")
    print("   kanban-cli --project /path/to/project summary")
    print()


def _print_tool_table() -> None:
    """Print the MCP client tool/config reference table."""
    rows = [
        ("Claude Code", "~/.claude.json or .mcp.json",
         "mcpServers"),
        ("Claude Desktop",
         "~/.config/Claude/claude_desktop_config.json",
         "mcpServers"),
        ("Gemini CLI", "~/.gemini/settings.json",
         "mcpServers"),
        ("VS Code / Copilot", ".vscode/mcp.json",
         "servers"),
        ("Codex CLI", "~/.codex/config.toml",
         "[mcp_servers.kanban]"),
        ("Cursor", ".cursor/mcp.json",
         "mcpServers"),
    ]
    hdr = f"   {'Tool':<20}{'Config file':<45}{'Key'}"
    sep = f"   {'────':<20}{'───────────':<45}{'───'}"
    print(hdr)
    print(sep)
    for tool, cfg, key in rows:
        print(f"   {tool:<20}{cfg:<45}{key}")


if __name__ == "__main__":
    main()
