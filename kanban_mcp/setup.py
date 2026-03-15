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

try:
    import mysql.connector
    from mysql.connector import Error as MySQLError
    _HAS_MYSQL = True
except ImportError:
    _HAS_MYSQL = False
    MySQLError = Exception  # fallback for type references

# Migrations numbered <= this are backfilled for pre-versioning installs
_BACKFILL_CUTOFF = 4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kanban-setup",
        description="Set up the database for kanban-mcp",
    )
    parser.add_argument(
        "--backend",
        choices=["mysql", "sqlite"],
        default=None,
        help=(
            "Database backend to use. Auto-detected if not set"
            " (MySQL if KANBAN_DB_* env vars present, else SQLite)."
        ),
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
        "--db-host", default=None, help="MySQL/MariaDB host",
    )
    parser.add_argument(
        "--db-port", default=None, help="MySQL/MariaDB port",
    )
    parser.add_argument(
        "--mysql-root-user", default=None,
        help="MySQL/MariaDB admin user for setup",
    )
    parser.add_argument(
        "--mysql-root-password", default=None,
        help="MySQL/MariaDB admin password",
    )
    parser.add_argument(
        "--migrate-only",
        action="store_true",
        help=(
            "Only run migrations (skip DB/user creation"
            " and .env writing). Useful for upgrades."
        ),
    )
    parser.add_argument(
        "--sqlite-path",
        default=None,
        help="SQLite database file path (default: XDG data dir)",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Show uninstall instructions",
    )
    return parser


def generate_password() -> str:
    """Generate a secure random password."""
    return secrets.token_urlsafe(16)


def find_migrations_dir(backend_type: str = "mysql") -> str | None:
    """Find the migrations directory for the given backend.

    Checks two locations:
    1. Local repo: ./kanban_mcp/migrations/{backend_type}
    2. Package install: alongside this file at
       kanban_mcp/migrations/{backend_type}

    Falls back to the flat migrations/ directory for backwards compatibility.
    """
    # Local repo check — new structure
    local = Path.cwd() / "kanban_mcp" / "migrations" / backend_type
    if local.is_dir() and list(local.glob("0*.sql")):
        return str(local)

    # Package install check — new structure
    package = Path(__file__).parent / "migrations" / backend_type
    if package.is_dir() and list(package.glob("0*.sql")):
        return str(package)

    # Fallback: flat migrations/ directory (backwards compat)
    local_flat = Path.cwd() / "kanban_mcp" / "migrations"
    if local_flat.is_dir() and list(local_flat.glob("0*.sql")):
        return str(local_flat)

    package_flat = Path(__file__).parent / "migrations"
    if package_flat.is_dir() and list(package_flat.glob("0*.sql")):
        return str(package_flat)

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
    db_port: str = "3306",
) -> None:
    """Write a .env file with kanban-mcp database configuration."""
    content = (
        "# kanban-mcp database configuration\n"
        f"KANBAN_DB_HOST={db_host}\n"
        f"KANBAN_DB_USER={db_user}\n"
        f"KANBAN_DB_PASSWORD={db_password}\n"
        f"KANBAN_DB_NAME={db_name}\n"
    )
    if db_port != "3306":
        content += f"KANBAN_DB_PORT={db_port}\n"
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
        "db_port": _resolve(
            args.db_port, "KANBAN_DB_PORT", "3306",
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
    db_port: str = "3306",
) -> str:
    """Return MCP config JSON string with explicit credentials."""
    env = {
        "KANBAN_DB_HOST": db_host,
        "KANBAN_DB_USER": db_user,
        "KANBAN_DB_PASSWORD": db_password,
        "KANBAN_DB_NAME": db_name,
    }
    if db_port != "3306":
        env["KANBAN_DB_PORT"] = db_port
    config = {
        "mcpServers": {
            "kanban": {
                "command": "kanban-mcp",
                "env": env,
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
    db_port = _prompt(
        "Database port", defaults["db_port"] or "3306",
    )
    mysql_root_user = _prompt(
        "MySQL/MariaDB root user for setup",
        defaults["mysql_root_user"] or "root",
    )
    mysql_root_password = _prompt(
        "MySQL/MariaDB root password (blank for socket auth)", "",
    )

    return {
        "db_name": db_name,
        "db_user": db_user,
        "db_password": db_password,
        "db_host": db_host,
        "db_port": db_port,
        "mysql_root_user": mysql_root_user,
        "mysql_root_password": mysql_root_password or None,
    }


def _find_mysql_socket() -> str | None:
    """Find the MySQL/MariaDB Unix socket path."""
    candidates = [
        "/var/run/mysqld/mysqld.sock",    # Debian/Ubuntu
        "/var/run/mariadb/mariadb.sock",  # MariaDB (Arch, Fedora)
        "/var/lib/mysql/mysql.sock",      # RHEL/CentOS
        "/tmp/mysql.sock",  # macOS (Homebrew)  # nosec B108
        "/var/mysql/mysql.sock",          # macOS (official)
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _print_auth_error(err: MySQLError, config: dict) -> None:
    """Print a friendly error for a MySQL/MariaDB error code."""
    user = config["mysql_root_user"]
    host = config["db_host"]
    errno = getattr(err, "errno", None)
    if errno == 1698:
        print(
            f"Error: Socket auth failed for '{user}'."
            f"\n  MySQL root uses the auth_socket plugin,"
            " which only works when the OS user matches"
            " the MySQL user (i.e. running as OS root)."
            "\n  Provide the root password via"
            " MYSQL_ROOT_PASSWORD or run"
            " `kanban-setup` interactively."
        )
    elif errno == 1045:
        print(
            f"Error: Access denied for '{user}'."
            "\n  Check your MySQL root password."
            " Set MYSQL_ROOT_PASSWORD or run"
            " `kanban-setup` interactively."
        )
    elif errno in (2002, 2003):
        print(
            f"Error: Cannot connect to MySQL/MariaDB at {host}."
            " Is the server running?"
        )
    else:
        print(
            f"Error: Could not connect to MySQL/MariaDB"
            f" as {user}: {err}"
            "\n  Try setting MYSQL_ROOT_PASSWORD or run"
            " `kanban-setup` interactively."
        )


def _create_database(config: dict) -> None:
    """Connect as MySQL/MariaDB root and create the database + user.

    On localhost without a root password, uses a fallback chain:
    1. Try Unix socket auth (Debian/Ubuntu default)
    2. If socket auth fails (1698/1045), try TCP with empty password
    3. If both fail, print specific guidance based on error code
    """
    is_local = config["db_host"] in ("localhost", "127.0.0.1")
    has_password = bool(config["mysql_root_password"])

    db_port = int(config.get("db_port", "3306"))

    connect_args = {
        "user": config["mysql_root_user"],
        "host": config["db_host"],
        "port": db_port,
    }
    if has_password:
        connect_args["password"] = config["mysql_root_password"]

    # On localhost without a password, try Unix socket auth
    # (Debian/Ubuntu default to auth_socket for root)
    if is_local and not has_password:
        sock = _find_mysql_socket()
        if sock:
            connect_args["unix_socket"] = sock
            # Remove host/port — socket and host are mutually exclusive
            connect_args.pop("host", None)
            connect_args.pop("port", None)

    print("Connecting to MySQL/MariaDB as root...")
    try:
        conn = mysql.connector.connect(**connect_args)
    except MySQLError as e:
        # On localhost with no password, socket auth may fail
        # because OS user != MySQL user. Try TCP with empty
        # password as fallback (works when root has no password).
        if is_local and not has_password and e.errno in (
            1698, 1045,
        ):
            print(
                "  Socket auth failed, trying TCP"
                " with empty password..."
            )
            tcp_args = {
                "user": config["mysql_root_user"],
                "host": config["db_host"],
                "port": db_port,
                "password": "",  # nosec B105
            }
            try:
                conn = mysql.connector.connect(**tcp_args)
            except MySQLError as tcp_err:
                # Both attempts failed — report the TCP error
                _print_auth_error(tcp_err, config)
                sys.exit(1)
        else:
            _print_auth_error(e, config)
            sys.exit(1)

    cursor = conn.cursor()
    db = config["db_name"]
    user = config["db_user"]
    pw = config["db_password"]
    # Escape single quotes for SQL string literals
    pw_escaped = pw.replace("'", "''")

    statements = [
        (
            f"CREATE DATABASE IF NOT EXISTS `{db}`"
            " CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        ),
        (
            f"CREATE USER IF NOT EXISTS '{user}'@'localhost'"
            f" IDENTIFIED BY '{pw_escaped}'"
        ),
        (
            f"CREATE USER IF NOT EXISTS '{user}'@'%'"
            f" IDENTIFIED BY '{pw_escaped}'"
        ),
        # ALTER USER ensures password is current even if the
        # user already existed (CREATE IF NOT EXISTS is a no-op
        # for existing users, leaving stale passwords).
        (
            f"ALTER USER '{user}'@'localhost'"
            f" IDENTIFIED BY '{pw_escaped}'"
        ),
        (
            f"ALTER USER '{user}'@'%'"
            f" IDENTIFIED BY '{pw_escaped}'"
        ),
        f"GRANT ALL PRIVILEGES ON `{db}`.* TO '{user}'@'localhost'",
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
    """Split a SQL script on semicolons, respecting quotes.

    Strips ``-- …`` line comments while preserving ``--`` that
    appears inside single-quoted string literals.
    """
    # 1. Strip comments, but not inside quotes
    cleaned_lines: list[str] = []
    for line in sql.splitlines():
        out: list[str] = []
        in_quote = False
        i = 0
        while i < len(line):
            ch = line[i]
            if ch == "\\" and in_quote:
                # backslash escape — consume next char as-is
                out.append(ch)
                if i + 1 < len(line):
                    i += 1
                    out.append(line[i])
            elif ch == "'" and not in_quote:
                in_quote = True
                out.append(ch)
            elif ch == "'" and in_quote:
                # handle escaped quote ('')
                if i + 1 < len(line) and line[i + 1] == "'":
                    out.append("''")
                    i += 1
                else:
                    in_quote = False
                    out.append(ch)
            elif ch == "-" and not in_quote:
                if i + 1 < len(line) and line[i + 1] == "-":
                    break  # rest of line is a comment
                out.append(ch)
            else:
                out.append(ch)
            i += 1
        cleaned_lines.append("".join(out))
    cleaned = "\n".join(cleaned_lines)

    # 2. Split on semicolons, respecting BEGIN...END blocks
    #    (needed for SQLite triggers: CREATE TRIGGER ... BEGIN ... END;)
    # BEGIN TRANSACTION / BEGIN IMMEDIATE / BEGIN DEFERRED / BEGIN EXCLUSIVE
    # are not trigger bodies — don't count them.
    _BEGIN_TRANSACTION_WORDS = {
        'TRANSACTION', 'IMMEDIATE', 'DEFERRED', 'EXCLUSIVE'}
    statements: list[str] = []
    current: list[str] = []
    in_begin_block = 0
    for part in cleaned.split(";"):
        stripped = part.strip()
        # Track BEGIN/END nesting
        upper = stripped.upper()
        # Count BEGIN keywords (but not BEGIN TRANSACTION etc.)
        tokens = upper.split()
        for i_tok, token in enumerate(tokens):
            if token == 'BEGIN':  # nosec B105
                nxt = i_tok + 1
                next_tok = (tokens[nxt]
                            if nxt < len(tokens)
                            else None)
                if next_tok not in _BEGIN_TRANSACTION_WORDS:
                    in_begin_block += 1
        current.append(part)
        if in_begin_block > 0:
            for token in upper.split():
                if token == 'END':  # nosec B105
                    in_begin_block -= 1
            if in_begin_block <= 0:
                in_begin_block = 0
                joined = ";".join(current).strip()
                if joined:
                    statements.append(joined)
                current = []
        else:
            joined = ";".join(current).strip()
            if joined:
                statements.append(joined)
            current = []
    # Handle any remaining
    if current:
        joined = ";".join(current).strip()
        if joined:
            statements.append(joined)
    return statements


def _ensure_schema_migrations_table(
    cursor, backend_type: str = 'mysql',
) -> None:
    """Create the schema_migrations tracking table if needed."""
    if backend_type == 'sqlite':
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TEXT DEFAULT (datetime('now'))
            )
        """)
    else:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename VARCHAR(255) PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
              COLLATE=utf8mb4_unicode_ci
        """)


def _get_applied_migrations(cursor) -> set[str]:
    """Return set of migration filenames already applied."""
    cursor.execute("SELECT filename FROM schema_migrations")
    return {row[0] for row in cursor.fetchall()}


def _backfill_existing_install(
    cursor, migration_files: list[Path],
    backend_type: str = 'mysql',
) -> bool:
    """Detect pre-versioning installs and backfill records.

    Returns True if backfill was performed.
    Only applies to MySQL — SQLite installs are always fresh.
    """
    if backend_type == 'sqlite':
        return False

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


def _run_migrations_with_backend(backend) -> None:
    """Run migrations using a DatabaseBackend instance (CLI mode)."""
    bt = backend.backend_type
    migrations_dir = find_migrations_dir(bt)
    if migrations_dir is None:
        print("Error: Could not find migration files.")
        print(
            "Run this from the kanban-mcp repo root,"
            " or ensure kanban-mcp is pip-installed."
        )
        sys.exit(1)

    migration_files = sorted(Path(migrations_dir).glob("0*.sql"))
    if not migration_files:
        print("Error: Could not find migration files.")
        sys.exit(1)

    print(
        f"Found {len(migration_files)} migration(s)"
        f" in: {migration_files[0].parent}"
    )

    try:
        with backend.db_cursor(commit=True) as cursor:
            _ensure_schema_migrations_table(cursor, bt)

        with backend.db_cursor(commit=True) as cursor:
            _backfill_existing_install(
                cursor, migration_files, bt)

        with backend.db_cursor() as cursor:
            applied = _get_applied_migrations(cursor)
    except Exception as e:
        print(f"Error setting up migrations: {e}")
        sys.exit(1)

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
            with backend.db_cursor(commit=True) as cursor:
                for stmt in _split_sql(sql):
                    try:
                        cursor.execute(stmt)
                        try:
                            cursor.fetchall()
                        except Exception:  # nosec B110
                            pass
                    except Exception as stmt_err:
                        is_mysql_1146 = (
                            hasattr(stmt_err, 'errno')
                            and stmt_err.errno == 1146)
                        is_sqlite_no_table = (
                            'no such table' in str(stmt_err))
                        if is_mysql_1146 or is_sqlite_no_table:
                            print(
                                f"    Skipped (table absent):"
                                f" {stmt_err}")
                            continue
                        raise
                cursor.execute(
                    "INSERT INTO schema_migrations"
                    f" (filename) VALUES"
                    f" ({backend.placeholder})",  # nosec B608
                    (mfile.name,),
                )
            applied_count += 1
        except Exception as e:
            print(f"  ERROR applying {mfile.name}: {e}")
            print(
                "  Aborting migrations."
                " Fix the issue and re-run."
            )
            sys.exit(1)

    print(
        f"Migrations complete."
        f" Applied: {applied_count},"
        f" already up-to-date: {skipped_count}."
    )


def _run_migrations(config: dict) -> None:
    """Connect as kanban user and run migrations with tracking.

    Legacy MySQL-only path for backward compat.
    """
    if not _HAS_MYSQL:
        print(
            "Error: mysql-connector-python not installed."
            " Install with: pip install kanban-mcp[mysql]"
        )
        sys.exit(1)

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

    db_port = int(config.get("db_port", "3306"))

    connect_args = {
        "user": config["db_user"],
        "password": config["db_password"],
        "host": config["db_host"],
        "port": db_port,
        "database": config["db_name"],
    }
    if config["db_host"] in ("localhost", "127.0.0.1"):
        sock = _find_mysql_socket()
        if sock:
            connect_args["unix_socket"] = sock
            connect_args.pop("host", None)
            connect_args.pop("port", None)

    try:
        conn = mysql.connector.connect(**connect_args)
    except MySQLError as e:
        print(
            f"Error: Could not connect as"
            f" {config['db_user']} to database"
            f" {config['db_name']}: {e}"
            "\n  Check credentials in"
            " ~/.config/kanban-mcp/.env"
        )
        sys.exit(1)

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
                try:
                    cursor.execute(stmt)
                    # Drain any result sets (e.g. from
                    # OPTIMIZE TABLE) so the next statement
                    # doesn't hit "Unread result found".
                    try:
                        cursor.fetchall()
                    except Exception:  # nosec B110
                        pass
                except MySQLError as stmt_err:
                    # 1146 = Table doesn't exist.  Skip
                    # gracefully — the table may be optional
                    # (e.g. embeddings without semantic search).
                    if stmt_err.errno == 1146:
                        tbl = getattr(stmt_err, "msg", str(stmt_err))
                        print(f"    Skipped (table absent): {tbl}")
                        continue
                    raise
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


def auto_migrate(backend_or_config) -> None:
    """Run pending migrations at server startup.

    Accepts either a DatabaseBackend instance or a legacy config dict.
    When given a dict, connects via MySQL (backward compatible).

    Unlike _run_migrations(), this function:
    - Logs instead of printing
    - Never calls sys.exit — errors are logged and swallowed
    - Is safe to call on every server start
    """
    from kanban_mcp.db.base import DatabaseBackend

    log = logging.getLogger("kanban-mcp.migrate")

    # Duck-type check: backend instance vs legacy config dict
    if isinstance(backend_or_config, DatabaseBackend):
        _auto_migrate_backend(backend_or_config, log)
    elif isinstance(backend_or_config, dict):
        import warnings
        warnings.warn(
            "Passing a config dict to auto_migrate() is deprecated."
            " Pass a DatabaseBackend instance instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        _auto_migrate_mysql_legacy(backend_or_config, log)
    else:
        log.error(
            "auto_migrate: expected DatabaseBackend or dict,"
            " got %s", type(backend_or_config).__name__,
        )


def _auto_migrate_backend(backend, log) -> None:
    """Run migrations using a DatabaseBackend instance."""
    bt = backend.backend_type
    migrations_dir = find_migrations_dir(bt)
    if migrations_dir is None:
        log.debug("No migration files found for %s, skipping.", bt)
        return

    migration_files = sorted(Path(migrations_dir).glob("0*.sql"))
    if not migration_files:
        log.debug("No migration files found, skipping.")
        return

    try:
        with backend.db_cursor(commit=True) as cursor:
            _ensure_schema_migrations_table(cursor, bt)

        with backend.db_cursor(commit=True) as cursor:
            _backfill_existing_install(cursor, migration_files, bt)

        with backend.db_cursor() as cursor:
            applied = _get_applied_migrations(cursor)

        for mfile in migration_files:
            if mfile.name in applied:
                continue

            log.info("Applying migration: %s", mfile.name)
            sql = mfile.read_text()
            try:
                with backend.db_cursor(commit=True) as cursor:
                    skipped = False
                    for stmt in _split_sql(sql):
                        try:
                            cursor.execute(stmt)
                            try:
                                cursor.fetchall()
                            except Exception:  # nosec B110
                                pass
                        except Exception as stmt_err:
                            # Skip "table absent" errors on both backends
                            is_mysql_1146 = (
                                hasattr(stmt_err, 'errno')
                                and stmt_err.errno == 1146)
                            is_sqlite_no_table = (
                                'no such table' in str(stmt_err))
                            if is_mysql_1146 or is_sqlite_no_table:
                                log.info(
                                    "  Skipped (table absent):"
                                    " %s", stmt_err,
                                )
                                skipped = True
                                continue
                            raise
                    if skipped:
                        log.warning(
                            "Migration %s had skipped statements"
                            " — marking as applied but review"
                            " may be needed.", mfile.name,
                        )
                    cursor.execute(
                        "INSERT INTO schema_migrations"
                        f" (filename) VALUES"
                        f" ({backend.placeholder})",  # nosec B608
                        (mfile.name,),
                    )
            except Exception as e:
                log.error(
                    "Migration %s failed: %s",
                    mfile.name, e,
                )
                raise
    except Exception as e:
        log.error("Auto-migrate error: %s", e)
        raise


def _auto_migrate_mysql_legacy(db_config: dict, log) -> None:
    """Legacy auto_migrate path for MySQL config dicts."""
    if not _HAS_MYSQL:
        log.error(
            "Auto-migrate: mysql-connector-python not installed.")
        return

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
                    try:
                        cursor.execute(stmt)
                        try:
                            cursor.fetchall()
                        except Exception:  # nosec B110
                            pass
                    except MySQLError as stmt_err:
                        if stmt_err.errno == 1146:
                            log.info(
                                "  Skipped (table absent):"
                                " %s", stmt_err,
                            )
                            continue
                        raise
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
                raise

        cursor.close()
    except MySQLError as e:
        log.error("Auto-migrate error: %s", e)
        raise
    finally:
        conn.close()


def _detect_backend() -> str:
    """Auto-detect backend: MySQL if creds present, else SQLite."""
    explicit = os.environ.get('KANBAN_BACKEND')
    if explicit:
        return explicit
    if (os.environ.get('KANBAN_DB_USER')
            and os.environ.get('KANBAN_DB_PASSWORD')
            and os.environ.get('KANBAN_DB_NAME')):
        return 'mysql'
    return 'sqlite'


def write_sqlite_env_file(path: str, sqlite_path: str = None) -> None:
    """Write a .env file with SQLite configuration."""
    content = (
        "# kanban-mcp database configuration\n"
        "KANBAN_BACKEND=sqlite\n"
    )
    if sqlite_path:
        content += f"KANBAN_SQLITE_PATH={sqlite_path}\n"
    Path(path).write_text(content)


def mcp_config_sqlite_json() -> str:
    """Return MCP config JSON for SQLite backend."""
    config = {
        "mcpServers": {
            "kanban": {
                "command": "kanban-mcp",
                "env": {
                    "KANBAN_BACKEND": "sqlite",
                },
            }
        }
    }
    return json.dumps(config, indent=2)


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
            db_port=config.get("db_port", "3306"),
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

    if args.uninstall:
        print("To uninstall kanban-mcp:")
        print()
        print("  pipx uninstall kanban-mcp")
        print()
        print("To also remove config and credentials:")
        from kanban_mcp.core import get_config_dir
        print(f"  rm -rf {get_config_dir()}")
        print()
        print(
            "To drop the MySQL/MariaDB database and user,"
            " connect as root and run:"
        )
        print("  DROP DATABASE IF EXISTS kanban;")
        print(
            "  DROP USER IF EXISTS"
            " 'kanban'@'localhost';"
        )
        print(
            "  DROP USER IF EXISTS"
            " 'kanban'@'%';"
        )
        return

    # Detect backend
    backend_type = args.backend or _detect_backend()
    print("=== kanban-mcp Database Setup ===")
    print(f"Backend: {backend_type}")
    print()

    if backend_type == 'sqlite':
        _setup_sqlite(args)
        return

    # MySQL setup path
    if not _HAS_MYSQL:
        print(
            "Error: mysql-connector-python not installed."
            "\n  Install with: pip install kanban-mcp[mysql]"
            "\n  Or use SQLite: kanban-setup --backend sqlite"
        )
        sys.exit(1)

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
    if config.get("db_port", "3306") != "3306":
        print(f"  Port:     {config['db_port']}")
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
        db_port=config.get("db_port", "3306"),
    ))
    print()
    print("2. Start the web UI (optional):")
    print("   kanban-web")
    print("   Open http://localhost:5000")
    print()
    print("3. Verify installation:")
    print("   kanban-cli --project /path/to/project summary")
    print()


def _setup_sqlite(args) -> None:
    """Set up SQLite backend — zero config, just run migrations."""
    from kanban_mcp.db.sqlite_backend import SQLiteBackend

    # Determine path
    sqlite_path = getattr(args, 'sqlite_path', None)
    if sqlite_path:
        backend = SQLiteBackend(db_path=sqlite_path)
    else:
        backend = SQLiteBackend()

    db_path = backend._db_path
    print(f"  Database: {db_path}")
    print()

    if not args.auto:
        confirm = _prompt("Proceed? [Y/n]", "Y")
        if not confirm.lower().startswith("y"):
            print("Aborted.")
            return

    # Run migrations
    print("--- Running migrations ---")
    _run_migrations_with_backend(backend)

    # Install semantic if requested
    if args.with_semantic:
        print()
        print("--- Installing semantic search dependencies ---")
        _install_semantic()

    # Write .env
    from kanban_mcp.core import get_config_dir
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    env_path = str(config_dir / ".env")

    write = True
    if os.path.exists(env_path) and not args.auto:
        overwrite = _prompt(
            f"{env_path} already exists. Overwrite? [y/N]", "N")
        if not overwrite.lower().startswith("y"):
            print("Skipping .env generation.")
            write = False

    if write:
        write_sqlite_env_file(env_path, sqlite_path)
        print(f"Created {env_path}")

    print()
    print("=== Setup complete ===")
    print()
    print("Next steps:")
    print()
    print("1. Add kanban-mcp to your MCP client config:")
    print()
    print(mcp_config_sqlite_json())
    print()
    print("   Add to the config file for your tool:")
    print()
    _print_tool_table()
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
    sep = f"   {'----':<20}{'-----------':<45}{'---'}"
    print(hdr)
    print(sep)
    for tool, cfg, key in rows:
        print(f"   {tool:<20}{cfg:<45}{key}")


if __name__ == "__main__":
    main()
