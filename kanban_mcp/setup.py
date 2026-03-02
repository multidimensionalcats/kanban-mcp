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
import os
import secrets
import subprocess
import sys
from pathlib import Path


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
        help="Also install semantic search dependencies (numpy, onnxruntime, etc.)",
    )
    parser.add_argument("--db-name", default=None, help="Database name")
    parser.add_argument("--db-user", default=None, help="Database user")
    parser.add_argument("--db-password", default=None, help="Database password")
    parser.add_argument("--db-host", default=None, help="MySQL host")
    parser.add_argument("--mysql-root-user", default=None, help="MySQL admin user for setup")
    parser.add_argument("--mysql-root-password", default=None, help="MySQL admin password")
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

    In auto mode, values come from CLI args first, then env vars, then defaults.
    In interactive mode, this provides defaults for the prompts.
    """
    def _resolve(cli_val, env_key, default):
        if cli_val is not None:
            return cli_val
        env_val = os.environ.get(env_key)
        if env_val:
            return env_val
        return default

    db_password = _resolve(args.db_password, "KANBAN_DB_PASSWORD", None)
    if db_password is None and args.auto:
        db_password = generate_password()

    return {
        "db_name": _resolve(args.db_name, "KANBAN_DB_NAME", "kanban"),
        "db_user": _resolve(args.db_user, "KANBAN_DB_USER", "kanban"),
        "db_password": db_password,
        "db_host": _resolve(args.db_host, "KANBAN_DB_HOST", "localhost"),
        "mysql_root_user": _resolve(args.mysql_root_user, "MYSQL_ROOT_USER", "root"),
        "mysql_root_password": _resolve(args.mysql_root_password, "MYSQL_ROOT_PASSWORD", None),
    }


def mcp_config_json(db_host: str, db_user: str, db_password: str, db_name: str) -> str:
    """Return MCP client config JSON string."""
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


def _prompt(message: str, default: str = "") -> str:
    """Prompt user for input with a default value."""
    if default:
        raw = input(f"{message} [{default}]: ").strip()
        return raw if raw else default
    return input(f"{message}: ").strip()


def _run_interactive(args: argparse.Namespace) -> dict:
    """Gather configuration interactively."""
    defaults = resolve_config(args)

    db_name = _prompt("Database name", defaults["db_name"] or "kanban")
    db_user = _prompt("Database user", defaults["db_user"] or "kanban")

    db_password = _prompt("Database password (leave blank to auto-generate)", "")
    if not db_password:
        db_password = generate_password()
        print(f"Generated password: {db_password}")

    db_host = _prompt("Database host", defaults["db_host"] or "localhost")
    mysql_root_user = _prompt("MySQL root user for setup", defaults["mysql_root_user"] or "root")
    mysql_root_password = _prompt("MySQL root password (blank for socket auth)", "")

    return {
        "db_name": db_name,
        "db_user": db_user,
        "db_password": db_password,
        "db_host": db_host,
        "mysql_root_user": mysql_root_user,
        "mysql_root_password": mysql_root_password or None,
    }


def _create_database(config: dict) -> None:
    """Connect as MySQL root and create the database + user."""
    import mysql.connector

    connect_args = {
        "user": config["mysql_root_user"],
        "host": config["db_host"],
    }
    if config["mysql_root_password"]:
        connect_args["password"] = config["mysql_root_password"]

    print("Connecting to MySQL as root...")
    try:
        conn = mysql.connector.connect(**connect_args)
    except mysql.connector.Error as e:
        print(f"Error: Could not connect to MySQL as {config['mysql_root_user']}: {e}")
        sys.exit(1)

    cursor = conn.cursor()
    db = config["db_name"]
    user = config["db_user"]
    pw = config["db_password"]

    statements = [
        f"CREATE DATABASE IF NOT EXISTS `{db}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci",
        f"CREATE USER IF NOT EXISTS '{user}'@'%' IDENTIFIED BY '{pw}'",
        f"GRANT ALL PRIVILEGES ON `{db}`.* TO '{user}'@'%'",
        "FLUSH PRIVILEGES",
    ]

    for stmt in statements:
        cursor.execute(stmt)

    conn.commit()
    cursor.close()
    conn.close()
    print("Database and user created.")


def _run_migrations(config: dict) -> None:
    """Connect as the kanban user and run all migration files."""
    import mysql.connector

    migration_files = get_migration_files()
    if not migration_files:
        print("Error: Could not find migration files.")
        print("Run this from the kanban-mcp repo root, or ensure kanban-mcp is pip-installed.")
        sys.exit(1)

    print(f"Found {len(migration_files)} migration(s) in: {migration_files[0].parent}")

    conn = mysql.connector.connect(
        user=config["db_user"],
        password=config["db_password"],
        host=config["db_host"],
        database=config["db_name"],
    )
    cursor = conn.cursor()

    for mfile in migration_files:
        print(f"  Applying {mfile.name}...")
        sql = mfile.read_text()
        # multi=True lets mysql.connector handle multiple statements
        for result in cursor.execute(sql, multi=True):
            # Must consume all results to actually execute them
            pass
        conn.commit()

    cursor.close()
    conn.close()
    print("Migrations complete.")


def _handle_env_file(config: dict, auto: bool) -> None:
    """Write .env file, prompting before overwrite in interactive mode."""
    env_path = os.path.join(os.getcwd(), ".env")
    write = True

    if os.path.exists(env_path):
        if auto:
            pass  # overwrite silently
        else:
            overwrite = _prompt(".env file already exists. Overwrite? [y/N]", "N")
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
    subprocess.check_call([sys.executable, "-m", "pip", "install", "kanban-mcp[semantic]"])
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
    print()
    print("=== Setup complete ===")
    print()
    print("Next steps:")
    print()
    print("1. Add kanban-mcp to your MCP client config:")
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
    print("   kanban-cli --project /path/to/your/project summary")
    print()


if __name__ == "__main__":
    main()
