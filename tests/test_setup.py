#!/usr/bin/env python3
"""
Unit tests for kanban-setup console script.
Tests non-DB logic: arg parsing, migration discovery,
password gen, .env writing, and migration versioning.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestArgParsing(unittest.TestCase):
    """Test argument parsing for interactive vs auto mode."""

    def setUp(self):
        from kanban_mcp.setup import build_parser
        self.parser = build_parser()

    def test_default_is_interactive(self):
        args = self.parser.parse_args([])
        self.assertFalse(args.auto)

    def test_auto_flag(self):
        args = self.parser.parse_args(["--auto"])
        self.assertTrue(args.auto)

    def test_with_semantic_flag(self):
        args = self.parser.parse_args(["--with-semantic"])
        self.assertTrue(args.with_semantic)

    def test_all_db_args(self):
        args = self.parser.parse_args([
            "--db-name", "mydb",
            "--db-user", "myuser",
            "--db-password", "mypass",
            "--db-host", "remotehost",
            "--mysql-root-user", "admin",
            "--mysql-root-password", "rootpass",
        ])
        self.assertEqual(args.db_name, "mydb")
        self.assertEqual(args.db_user, "myuser")
        self.assertEqual(args.db_password, "mypass")
        self.assertEqual(args.db_host, "remotehost")
        self.assertEqual(args.mysql_root_user, "admin")
        self.assertEqual(args.mysql_root_password, "rootpass")

    def test_db_port_arg(self):
        args = self.parser.parse_args(["--db-port", "3307"])
        self.assertEqual(args.db_port, "3307")

    def test_db_port_default_none(self):
        args = self.parser.parse_args([])
        self.assertIsNone(args.db_port)

    def test_defaults(self):
        args = self.parser.parse_args([])
        self.assertIsNone(args.db_name)
        self.assertIsNone(args.db_user)
        self.assertIsNone(args.db_password)
        self.assertIsNone(args.db_host)
        self.assertIsNone(args.mysql_root_user)
        self.assertIsNone(args.mysql_root_password)


class TestPasswordGeneration(unittest.TestCase):
    """Test password auto-generation."""

    def test_generate_password_returns_string(self):
        from kanban_mcp.setup import generate_password
        pw = generate_password()
        self.assertIsInstance(pw, str)

    def test_generate_password_sufficient_length(self):
        from kanban_mcp.setup import generate_password
        pw = generate_password()
        self.assertGreaterEqual(len(pw), 16)

    def test_generate_password_unique(self):
        from kanban_mcp.setup import generate_password
        passwords = {generate_password() for _ in range(10)}
        self.assertEqual(len(passwords), 10)


class TestMigrationDiscovery(unittest.TestCase):
    """Test finding migration SQL files."""

    def test_find_migrations_from_local_repo(self):
        from kanban_mcp.setup import find_migrations_dir
        repo_root = Path(__file__).parent.parent
        migrations_dir = repo_root / "kanban_mcp" / "migrations"
        if migrations_dir.exists():
            result = find_migrations_dir()
            self.assertIsNotNone(result)
            self.assertTrue(Path(result).is_dir())

    def test_find_migrations_returns_dir_with_sql_files(self):
        from kanban_mcp.setup import find_migrations_dir
        result = find_migrations_dir()
        if result is not None:
            sql_files = sorted(Path(result).glob("0*.sql"))
            self.assertGreater(len(sql_files), 0)

    def test_get_migration_files_sorted(self):
        from kanban_mcp.setup import get_migration_files
        files = get_migration_files()
        if files:
            names = [f.name for f in files]
            self.assertEqual(names, sorted(names))
            self.assertTrue(
                all(f.suffix == ".sql" for f in files),
            )


class TestEnvFileWriting(unittest.TestCase):
    """Test .env file generation."""

    def test_write_env_file(self):
        from kanban_mcp.setup import write_env_file
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = os.path.join(tmpdir, ".env")
            write_env_file(
                env_path,
                db_host="localhost",
                db_user="kanban",
                db_password="secret123",
                db_name="kanban",
            )
            self.assertTrue(os.path.exists(env_path))
            content = Path(env_path).read_text()
            self.assertIn("KANBAN_DB_HOST=localhost", content)
            self.assertIn("KANBAN_DB_USER=kanban", content)
            self.assertIn(
                "KANBAN_DB_PASSWORD=secret123", content,
            )
            self.assertIn("KANBAN_DB_NAME=kanban", content)

    def test_write_env_file_does_not_have_trailing_spaces(self):
        from kanban_mcp.setup import write_env_file
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = os.path.join(tmpdir, ".env")
            write_env_file(
                env_path, "localhost", "kanban", "pw", "kanban",
            )
            for line in Path(env_path).read_text().splitlines():
                if line.strip():
                    self.assertEqual(line, line.rstrip())


class TestConfigGathering(unittest.TestCase):
    """Test config resolution from args, env vars, and defaults."""

    def test_auto_mode_uses_env_vars(self):
        from kanban_mcp.setup import resolve_config, build_parser
        parser = build_parser()
        args = parser.parse_args(["--auto"])
        env = {
            "KANBAN_DB_NAME": "envdb",
            "KANBAN_DB_USER": "envuser",
            "KANBAN_DB_PASSWORD": "envpass",
            "KANBAN_DB_HOST": "envhost",
            "MYSQL_ROOT_USER": "envroot",
            "MYSQL_ROOT_PASSWORD": "envrootpw",
        }
        with patch.dict(os.environ, env, clear=False):
            config = resolve_config(args)
        self.assertEqual(config["db_name"], "envdb")
        self.assertEqual(config["db_user"], "envuser")
        self.assertEqual(config["db_password"], "envpass")
        self.assertEqual(config["db_host"], "envhost")
        self.assertEqual(config["mysql_root_user"], "envroot")
        self.assertEqual(
            config["mysql_root_password"], "envrootpw",
        )

    def test_auto_mode_cli_args_override_env(self):
        from kanban_mcp.setup import resolve_config, build_parser
        parser = build_parser()
        args = parser.parse_args([
            "--auto",
            "--db-name", "clidb",
            "--db-user", "cliuser",
        ])
        env = {
            "KANBAN_DB_NAME": "envdb",
            "KANBAN_DB_USER": "envuser",
        }
        with patch.dict(os.environ, env, clear=False):
            config = resolve_config(args)
        self.assertEqual(config["db_name"], "clidb")
        self.assertEqual(config["db_user"], "cliuser")

    def test_auto_mode_defaults(self):
        from kanban_mcp.setup import resolve_config, build_parser
        parser = build_parser()
        args = parser.parse_args(["--auto"])
        env_clear = {
            "KANBAN_DB_NAME": "",
            "KANBAN_DB_USER": "",
            "KANBAN_DB_PASSWORD": "",
            "KANBAN_DB_HOST": "",
            "MYSQL_ROOT_USER": "",
            "MYSQL_ROOT_PASSWORD": "",
        }
        with patch.dict(os.environ, env_clear, clear=False):
            for k in env_clear:
                os.environ.pop(k, None)
            config = resolve_config(args)
        self.assertEqual(config["db_name"], "kanban")
        self.assertEqual(config["db_user"], "kanban")
        self.assertEqual(config["db_host"], "localhost")
        self.assertEqual(config["mysql_root_user"], "root")
        self.assertIsNotNone(config["db_password"])
        self.assertGreaterEqual(len(config["db_password"]), 16)


class TestGetConfigDir(unittest.TestCase):
    """Test the shared get_config_dir() helper."""

    def test_linux_default(self):
        from kanban_mcp.core import get_config_dir
        with patch("sys.platform", "linux"), \
             patch.dict(os.environ, {}, clear=False):
            os.environ.pop("XDG_CONFIG_HOME", None)
            result = get_config_dir()
            self.assertEqual(
                result,
                Path.home() / ".config" / "kanban-mcp",
            )

    def test_linux_xdg_override(self):
        from kanban_mcp.core import get_config_dir
        with patch("sys.platform", "linux"), \
             patch.dict(
                 os.environ,
                 {"XDG_CONFIG_HOME": "/tmp/xdg"},
                 clear=False,
             ):
            result = get_config_dir()
            self.assertEqual(
                result, Path("/tmp/xdg/kanban-mcp"),
            )

    def test_windows(self):
        from kanban_mcp.core import get_config_dir
        appdata = "C:\\Users\\test\\AppData\\Roaming"
        with patch("sys.platform", "win32"), \
             patch.dict(
                 os.environ,
                 {"APPDATA": appdata},
                 clear=False,
             ):
            result = get_config_dir()
            self.assertEqual(result.name, "kanban-mcp")
            self.assertTrue(str(result).startswith("C:"))

    def test_returns_path_object(self):
        from kanban_mcp.core import get_config_dir
        result = get_config_dir()
        self.assertIsInstance(result, Path)


class TestHandleEnvFileConfigDir(unittest.TestCase):
    """Test _handle_env_file writes to config dir, not CWD."""

    def test_writes_to_config_dir(self):
        from kanban_mcp.setup import _handle_env_file
        config = {
            "db_host": "localhost",
            "db_user": "kanban",
            "db_password": "secret",
            "db_name": "kanban",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "kanban-mcp"
            with patch(
                "kanban_mcp.core.get_config_dir",
                return_value=config_dir,
            ):
                _handle_env_file(config, auto=True)
            env_path = config_dir / ".env"
            self.assertTrue(env_path.exists())
            content = env_path.read_text()
            self.assertIn(
                "KANBAN_DB_PASSWORD=secret", content,
            )

    def test_does_not_write_to_cwd(self):
        from kanban_mcp.setup import _handle_env_file
        config = {
            "db_host": "localhost",
            "db_user": "kanban",
            "db_password": "secret",
            "db_name": "kanban",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "kanban-mcp"
            cwd_env = Path(tmpdir) / "cwd" / ".env"
            with patch(
                "kanban_mcp.core.get_config_dir",
                return_value=config_dir,
            ), patch(
                "os.getcwd",
                return_value=str(Path(tmpdir) / "cwd"),
            ):
                _handle_env_file(config, auto=True)
            self.assertFalse(cwd_env.exists())

    def test_creates_config_dir_if_missing(self):
        from kanban_mcp.setup import _handle_env_file
        config = {
            "db_host": "localhost",
            "db_user": "kanban",
            "db_password": "secret",
            "db_name": "kanban",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = (
                Path(tmpdir) / "deep" / "nested" / "kanban-mcp"
            )
            with patch(
                "kanban_mcp.core.get_config_dir",
                return_value=config_dir,
            ):
                _handle_env_file(config, auto=True)
            self.assertTrue(config_dir.exists())
            self.assertTrue((config_dir / ".env").exists())


class TestMcpConfigOutput(unittest.TestCase):
    """Test the MCP config JSON output helper."""

    def test_mcp_config_json(self):
        import json
        from kanban_mcp.setup import mcp_config_json
        result = mcp_config_json(
            "localhost", "kanban", "pw123", "kanban",
        )
        parsed = json.loads(result)
        self.assertIn("mcpServers", parsed)
        self.assertEqual(
            parsed["mcpServers"]["kanban"]["env"][
                "KANBAN_DB_PASSWORD"
            ],
            "pw123",
        )


class TestMigrateOnlyFlag(unittest.TestCase):
    """Test --migrate-only argument parsing."""

    def setUp(self):
        from kanban_mcp.setup import build_parser
        self.parser = build_parser()

    def test_migrate_only_flag_exists(self):
        args = self.parser.parse_args(["--migrate-only"])
        self.assertTrue(args.migrate_only)

    def test_migrate_only_default_false(self):
        args = self.parser.parse_args([])
        self.assertFalse(args.migrate_only)

    def test_migrate_only_with_auto(self):
        args = self.parser.parse_args(
            ["--migrate-only", "--auto"],
        )
        self.assertTrue(args.migrate_only)
        self.assertTrue(args.auto)


class TestEnsureSchemaMigrationsTable(unittest.TestCase):
    """Test _ensure_schema_migrations_table creates tracking table."""

    def test_creates_table(self):
        from kanban_mcp.setup import (
            _ensure_schema_migrations_table,
        )
        mock_cursor = MagicMock()
        _ensure_schema_migrations_table(mock_cursor)
        mock_cursor.execute.assert_called_once()
        sql = mock_cursor.execute.call_args[0][0]
        self.assertIn(
            "CREATE TABLE IF NOT EXISTS schema_migrations",
            sql,
        )
        self.assertIn("filename", sql)
        self.assertIn("applied_at", sql)


class TestGetAppliedMigrations(unittest.TestCase):
    """Test _get_applied_migrations returns set of filenames."""

    def test_returns_set_of_filenames(self):
        from kanban_mcp.setup import _get_applied_migrations
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("001_initial_schema.sql",),
            ("002_add_fulltext_search.sql",),
        ]
        result = _get_applied_migrations(mock_cursor)
        self.assertEqual(result, {
            "001_initial_schema.sql",
            "002_add_fulltext_search.sql",
        })

    def test_returns_empty_set_when_none_applied(self):
        from kanban_mcp.setup import _get_applied_migrations
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        result = _get_applied_migrations(mock_cursor)
        self.assertEqual(result, set())


class TestBackfillExistingInstall(unittest.TestCase):
    """Test _backfill_existing_install detects existing DBs."""

    def test_backfills_when_items_exists_no_records(self):
        from kanban_mcp.setup import _backfill_existing_install
        mock_cursor = MagicMock()
        # items table exists, schema_migrations empty
        mock_cursor.fetchone.side_effect = [
            ("items",), (0,),
        ]
        migration_files = [
            Path("migrations/001_initial_schema.sql"),
            Path("migrations/002_add_fulltext_search.sql"),
            Path("migrations/003_add_embeddings.sql"),
            Path("migrations/004_add_cascades_and_indexes.sql"),
        ]
        result = _backfill_existing_install(
            mock_cursor, migration_files,
        )
        self.assertTrue(result)
        insert_calls = [
            c for c in mock_cursor.execute.call_args_list
            if "INSERT" in str(c)
        ]
        self.assertEqual(len(insert_calls), 4)

    def test_no_backfill_on_fresh_install(self):
        from kanban_mcp.setup import _backfill_existing_install
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        migration_files = [
            Path("migrations/001_initial_schema.sql"),
        ]
        result = _backfill_existing_install(
            mock_cursor, migration_files,
        )
        self.assertFalse(result)

    def test_no_backfill_when_already_recorded(self):
        from kanban_mcp.setup import _backfill_existing_install
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [
            ("items",), (3,),
        ]
        migration_files = [
            Path("migrations/001_initial_schema.sql"),
        ]
        result = _backfill_existing_install(
            mock_cursor, migration_files,
        )
        self.assertFalse(result)

    def test_backfill_only_up_to_004(self):
        """Backfill should NOT include 005+."""
        from kanban_mcp.setup import _backfill_existing_install
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [
            ("items",), (0,),
        ]
        migration_files = [
            Path("migrations/001_initial_schema.sql"),
            Path("migrations/002_add_fulltext_search.sql"),
            Path("migrations/003_add_embeddings.sql"),
            Path("migrations/004_add_cascades_and_indexes.sql"),
            Path("migrations/005_future_migration.sql"),
        ]
        result = _backfill_existing_install(
            mock_cursor, migration_files,
        )
        self.assertTrue(result)
        insert_calls = [
            c for c in mock_cursor.execute.call_args_list
            if "INSERT" in str(c)
        ]
        self.assertEqual(len(insert_calls), 4)
        all_sql = " ".join(str(c) for c in insert_calls)
        self.assertNotIn("005_future_migration.sql", all_sql)


class TestRunMigrationsVersioning(unittest.TestCase):
    """Test _run_migrations versioning: skip/apply correctly."""

    @patch("kanban_mcp.setup.get_migration_files")
    @patch("kanban_mcp.setup.mysql.connector")
    def test_skips_already_applied(
        self, mock_mysql, mock_get_files,
    ):
        from kanban_mcp.setup import _run_migrations

        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "001_initial_schema.sql"
            f2 = Path(tmpdir) / "002_add_fulltext_search.sql"
            f1.write_text(
                "CREATE TABLE IF NOT EXISTS items (id INT);",
            )
            f2.write_text(
                "ALTER TABLE items ADD FULLTEXT INDEX idx"
                " (title);",
            )
            mock_get_files.return_value = [f1, f2]

            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_mysql.connect.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor

            # no items table (fresh) but 001 already applied
            mock_cursor.fetchone.return_value = None
            mock_cursor.fetchall.return_value = [
                ("001_initial_schema.sql",),
            ]

            config = {
                "db_user": "kanban", "db_password": "pw",
                "db_host": "localhost", "db_name": "kanban",
            }
            _run_migrations(config)

            execute_calls = [
                str(c)
                for c in mock_cursor.execute.call_args_list
            ]
            executed_sql = " ".join(execute_calls)
            self.assertIn(
                "002_add_fulltext_search.sql", executed_sql,
            )

    @patch("kanban_mcp.setup.get_migration_files")
    @patch("kanban_mcp.setup.mysql.connector")
    def test_records_newly_applied(
        self, mock_mysql, mock_get_files,
    ):
        from kanban_mcp.setup import _run_migrations

        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "001_initial_schema.sql"
            f1.write_text(
                "CREATE TABLE IF NOT EXISTS items (id INT);",
            )
            mock_get_files.return_value = [f1]

            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_mysql.connect.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor

            mock_cursor.fetchone.return_value = None
            mock_cursor.fetchall.return_value = []

            config = {
                "db_user": "kanban", "db_password": "pw",
                "db_host": "localhost", "db_name": "kanban",
            }
            _run_migrations(config)

            execute_calls = [
                str(c)
                for c in mock_cursor.execute.call_args_list
            ]
            executed_sql = " ".join(execute_calls)
            self.assertIn(
                "INSERT INTO schema_migrations",
                executed_sql,
            )
            self.assertIn(
                "001_initial_schema.sql", executed_sql,
            )

    @patch("kanban_mcp.setup.get_migration_files")
    @patch("kanban_mcp.setup.mysql.connector")
    def test_stops_on_migration_failure(
        self, mock_mysql, mock_get_files,
    ):
        from kanban_mcp.setup import _run_migrations
        from mysql.connector import Error as RealMySQLError

        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "001_initial_schema.sql"
            f2 = Path(tmpdir) / "002_add_fulltext_search.sql"
            f1.write_text("BAD SQL;")
            f2.write_text("GOOD SQL;")
            mock_get_files.return_value = [f1, f2]

            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_mysql.connect.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor

            mock_cursor.fetchone.return_value = None
            mock_cursor.fetchall.return_value = []

            def execute_side_effect(sql, **kwargs):
                if "BAD SQL" in sql:
                    raise RealMySQLError("Syntax error")
                return MagicMock()

            mock_cursor.execute.side_effect = (
                execute_side_effect
            )

            config = {
                "db_user": "kanban", "db_password": "pw",
                "db_host": "localhost", "db_name": "kanban",
            }

            with self.assertRaises(SystemExit):
                _run_migrations(config)


class TestMainMigrateOnly(unittest.TestCase):
    """Test --migrate-only skips DB creation and .env."""

    @patch("kanban_mcp.setup._run_migrations")
    @patch("kanban_mcp.setup._create_database")
    @patch("kanban_mcp.setup._handle_env_file")
    @patch("kanban_mcp.setup.resolve_config")
    def test_migrate_only_skips_db_creation_and_env(
        self, mock_resolve, mock_env,
        mock_create_db, mock_migrations,
    ):
        from kanban_mcp.setup import main
        mock_resolve.return_value = {
            "db_name": "kanban", "db_user": "kanban",
            "db_password": "pw", "db_host": "localhost",
            "mysql_root_user": "root",
            "mysql_root_password": None,
        }
        with patch(
            "sys.argv",
            ["kanban-setup", "--migrate-only", "--auto"],
        ):
            main()

        mock_create_db.assert_not_called()
        mock_env.assert_not_called()
        mock_migrations.assert_called_once()


class TestAutoMigrate(unittest.TestCase):
    """Test auto_migrate() for use at server startup."""

    @patch("kanban_mcp.setup.get_migration_files")
    @patch("kanban_mcp.setup.mysql.connector")
    def test_applies_pending_migrations(
        self, mock_mysql, mock_get_files,
    ):
        from kanban_mcp.setup import auto_migrate

        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "001_initial_schema.sql"
            f1.write_text("CREATE TABLE items (id INT);")
            mock_get_files.return_value = [f1]

            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_mysql.connect.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor

            mock_cursor.fetchone.return_value = None
            mock_cursor.fetchall.return_value = []

            db_config = {
                "host": "localhost",
                "user": "kanban",
                "password": "pw",
                "database": "kanban",
            }
            auto_migrate(db_config)

            execute_calls = " ".join(
                str(c)
                for c in mock_cursor.execute.call_args_list
            )
            self.assertIn(
                "INSERT INTO schema_migrations",
                execute_calls,
            )

    @patch("kanban_mcp.setup.get_migration_files")
    @patch("kanban_mcp.setup.mysql.connector")
    def test_skips_when_all_applied(
        self, mock_mysql, mock_get_files,
    ):
        from kanban_mcp.setup import auto_migrate

        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "001_initial_schema.sql"
            f1.write_text("CREATE TABLE items (id INT);")
            mock_get_files.return_value = [f1]

            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_mysql.connect.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor

            mock_cursor.fetchone.return_value = None
            mock_cursor.fetchall.return_value = [
                ("001_initial_schema.sql",),
            ]

            db_config = {
                "host": "localhost",
                "user": "kanban",
                "password": "pw",
                "database": "kanban",
            }
            auto_migrate(db_config)

            execute_calls = " ".join(
                str(c)
                for c in mock_cursor.execute.call_args_list
            )
            self.assertNotIn(
                "INSERT INTO schema_migrations",
                execute_calls,
            )

    @patch("kanban_mcp.setup.get_migration_files")
    @patch("kanban_mcp.setup.mysql.connector")
    def test_does_not_crash_server_on_failure(
        self, mock_mysql, mock_get_files,
    ):
        """auto_migrate should log errors, not sys.exit."""
        from kanban_mcp.setup import auto_migrate
        from mysql.connector import Error as RealMySQLError

        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "001_initial_schema.sql"
            f1.write_text("BAD SQL;")
            mock_get_files.return_value = [f1]

            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_mysql.connect.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor

            mock_cursor.fetchone.return_value = None
            mock_cursor.fetchall.return_value = []

            def execute_side_effect(sql, **kwargs):
                if "BAD SQL" in sql:
                    raise RealMySQLError("Syntax error")
                return MagicMock()

            mock_cursor.execute.side_effect = (
                execute_side_effect
            )

            db_config = {
                "host": "localhost",
                "user": "kanban",
                "password": "pw",
                "database": "kanban",
            }
            # Should NOT raise or sys.exit
            auto_migrate(db_config)

    @patch("kanban_mcp.setup.get_migration_files")
    def test_no_migration_files_does_not_crash(
        self, mock_get_files,
    ):
        from kanban_mcp.setup import auto_migrate
        mock_get_files.return_value = []
        db_config = {
            "host": "localhost",
            "user": "kanban",
            "password": "pw",
            "database": "kanban",
        }
        # Should not raise
        auto_migrate(db_config)


class TestSplitSql(unittest.TestCase):
    """Test _split_sql helper."""

    def test_single_statement(self):
        from kanban_mcp.setup import _split_sql
        result = _split_sql("CREATE TABLE foo (id INT);")
        self.assertEqual(result, ["CREATE TABLE foo (id INT)"])

    def test_multiple_statements(self):
        from kanban_mcp.setup import _split_sql
        sql = (
            "ALTER TABLE a ADD INDEX x (y);\n"
            "ALTER TABLE b ADD INDEX z (w);"
        )
        result = _split_sql(sql)
        self.assertEqual(result, [
            "ALTER TABLE a ADD INDEX x (y)",
            "ALTER TABLE b ADD INDEX z (w)",
        ])

    def test_trailing_whitespace_and_semicolons(self):
        from kanban_mcp.setup import _split_sql
        result = _split_sql("SELECT 1;\n\n  ;  \n")
        self.assertEqual(result, ["SELECT 1"])

    def test_empty_string(self):
        from kanban_mcp.setup import _split_sql
        self.assertEqual(_split_sql(""), [])

    def test_comments_stripped(self):
        from kanban_mcp.setup import _split_sql
        sql = "-- comment\nCREATE TABLE foo (id INT);"
        result = _split_sql(sql)
        self.assertEqual(len(result), 1)
        self.assertIn("CREATE TABLE", result[0])

    def test_inline_comment_stripped(self):
        from kanban_mcp.setup import _split_sql
        sql = "SELECT 1; -- trailing comment\nSELECT 2;"
        result = _split_sql(sql)
        self.assertEqual(result, ["SELECT 1", "SELECT 2"])

    def test_double_dash_inside_quotes_preserved(self):
        from kanban_mcp.setup import _split_sql
        sql = "INSERT INTO t VALUES ('a -- b');"
        result = _split_sql(sql)
        self.assertEqual(result, ["INSERT INTO t VALUES ('a -- b')"])

    def test_escaped_quotes(self):
        from kanban_mcp.setup import _split_sql
        sql = "INSERT INTO t VALUES ('it''s -- ok');"
        result = _split_sql(sql)
        self.assertEqual(result, ["INSERT INTO t VALUES ('it''s -- ok')"])

    def test_backslash_escaped_quote(self):
        from kanban_mcp.setup import _split_sql
        sql = "INSERT INTO t VALUES ('it\\'s -- ok');"
        result = _split_sql(sql)
        self.assertEqual(
            result,
            ["INSERT INTO t VALUES ('it\\'s -- ok')"],
        )

    def test_backslash_escaped_backslash(self):
        from kanban_mcp.setup import _split_sql
        sql = "INSERT INTO t VALUES ('path\\\\dir');"
        result = _split_sql(sql)
        self.assertEqual(
            result,
            ["INSERT INTO t VALUES ('path\\\\dir')"],
        )


class TestFindMysqlSocket(unittest.TestCase):
    """Test _find_mysql_socket helper."""

    @patch("os.path.exists")
    def test_finds_debian_socket(self, mock_exists):
        from kanban_mcp.setup import _find_mysql_socket
        mock_exists.side_effect = lambda p: (
            p == "/var/run/mysqld/mysqld.sock"
        )
        self.assertEqual(
            _find_mysql_socket(),
            "/var/run/mysqld/mysqld.sock",
        )

    @patch("os.path.exists")
    def test_finds_rhel_socket(self, mock_exists):
        from kanban_mcp.setup import _find_mysql_socket
        mock_exists.side_effect = lambda p: (
            p == "/var/lib/mysql/mysql.sock"
        )
        self.assertEqual(
            _find_mysql_socket(),
            "/var/lib/mysql/mysql.sock",
        )

    @patch("os.path.exists")
    def test_returns_none_when_no_socket(self, mock_exists):
        from kanban_mcp.setup import _find_mysql_socket
        mock_exists.return_value = False
        self.assertIsNone(_find_mysql_socket())

    @patch("os.path.exists")
    def test_returns_first_match(self, mock_exists):
        from kanban_mcp.setup import _find_mysql_socket
        # Both Debian and RHEL sockets exist
        mock_exists.side_effect = lambda p: p in (
            "/var/run/mysqld/mysqld.sock",
            "/var/lib/mysql/mysql.sock",
        )
        # Should return Debian (first in list)
        self.assertEqual(
            _find_mysql_socket(),
            "/var/run/mysqld/mysqld.sock",
        )


class TestCreateDatabaseSocketAuth(unittest.TestCase):
    """Test _create_database uses socket auth on localhost."""

    @patch("kanban_mcp.setup._find_mysql_socket")
    @patch("kanban_mcp.setup.mysql.connector")
    def test_uses_socket_on_localhost_no_password(
        self, mock_mysql, mock_find_sock,
    ):
        from kanban_mcp.setup import _create_database
        mock_find_sock.return_value = (
            "/var/run/mysqld/mysqld.sock"
        )
        mock_conn = MagicMock()
        mock_mysql.connect.return_value = mock_conn
        mock_conn.cursor.return_value = MagicMock()

        config = {
            "db_name": "kanban", "db_user": "kanban",
            "db_password": "pw", "db_host": "localhost",
            "mysql_root_user": "root",
            "mysql_root_password": None,
        }
        _create_database(config)

        call_kwargs = mock_mysql.connect.call_args
        connect_args = call_kwargs[1] if call_kwargs[1] else (
            call_kwargs[0][0] if call_kwargs[0] else {}
        )
        self.assertIn(
            "unix_socket", connect_args,
        )
        self.assertNotIn("host", connect_args)

    @patch("kanban_mcp.setup._find_mysql_socket")
    @patch("kanban_mcp.setup.mysql.connector")
    def test_no_socket_when_password_provided(
        self, mock_mysql, mock_find_sock,
    ):
        from kanban_mcp.setup import _create_database
        mock_find_sock.return_value = (
            "/var/run/mysqld/mysqld.sock"
        )
        mock_conn = MagicMock()
        mock_mysql.connect.return_value = mock_conn
        mock_conn.cursor.return_value = MagicMock()

        config = {
            "db_name": "kanban", "db_user": "kanban",
            "db_password": "pw", "db_host": "localhost",
            "mysql_root_user": "root",
            "mysql_root_password": "rootpw",
        }
        _create_database(config)

        call_kwargs = mock_mysql.connect.call_args
        connect_args = call_kwargs[1] if call_kwargs[1] else (
            call_kwargs[0][0] if call_kwargs[0] else {}
        )
        self.assertNotIn("unix_socket", connect_args)

    @patch("kanban_mcp.setup._find_mysql_socket")
    @patch("kanban_mcp.setup.mysql.connector")
    def test_no_socket_on_remote_host(
        self, mock_mysql, mock_find_sock,
    ):
        from kanban_mcp.setup import _create_database
        mock_conn = MagicMock()
        mock_mysql.connect.return_value = mock_conn
        mock_conn.cursor.return_value = MagicMock()

        config = {
            "db_name": "kanban", "db_user": "kanban",
            "db_password": "pw", "db_host": "db.example.com",
            "mysql_root_user": "root",
            "mysql_root_password": "rootpw",
        }
        _create_database(config)

        mock_find_sock.assert_not_called()

    @patch("kanban_mcp.setup._find_mysql_socket")
    @patch("kanban_mcp.setup.mysql.connector")
    def test_creates_both_localhost_and_wildcard_users(
        self, mock_mysql, mock_find_sock,
    ):
        from kanban_mcp.setup import _create_database
        mock_find_sock.return_value = None
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_mysql.connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        config = {
            "db_name": "testdb", "db_user": "testuser",
            "db_password": "pw", "db_host": "localhost",
            "mysql_root_user": "root",
            "mysql_root_password": "rootpw",
        }
        _create_database(config)

        executed = [
            str(c) for c in mock_cursor.execute.call_args_list
        ]
        all_sql = " ".join(executed)
        self.assertIn("'testuser'@'localhost'", all_sql)
        self.assertIn("'testuser'@'%'", all_sql)
        # CREATE, ALTER, and GRANT for each
        self.assertIn(
            "CREATE USER IF NOT EXISTS 'testuser'@'localhost'",
            all_sql,
        )
        self.assertIn(
            "ALTER USER 'testuser'@'localhost'",
            all_sql,
        )
        self.assertIn(
            "ALTER USER 'testuser'@'%'",
            all_sql,
        )
        self.assertIn(
            "GRANT ALL PRIVILEGES ON `testdb`.*"
            " TO 'testuser'@'localhost'",
            all_sql,
        )


class TestRunMigrationsSocketAuth(unittest.TestCase):
    """Test _run_migrations uses socket on localhost."""

    @patch("kanban_mcp.setup._find_mysql_socket")
    @patch("kanban_mcp.setup.get_migration_files")
    @patch("kanban_mcp.setup.mysql.connector")
    def test_uses_socket_on_localhost(
        self, mock_mysql, mock_get_files, mock_find_sock,
    ):
        from kanban_mcp.setup import _run_migrations

        mock_find_sock.return_value = (
            "/var/run/mysqld/mysqld.sock"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "001_initial_schema.sql"
            f1.write_text("CREATE TABLE items (id INT);")
            mock_get_files.return_value = [f1]

            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_mysql.connect.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchone.return_value = None
            mock_cursor.fetchall.return_value = []

            config = {
                "db_user": "kanban", "db_password": "pw",
                "db_host": "localhost", "db_name": "kanban",
            }
            _run_migrations(config)

            call_kwargs = mock_mysql.connect.call_args[1]
            self.assertIn("unix_socket", call_kwargs)
            self.assertNotIn("host", call_kwargs)

    @patch("kanban_mcp.setup._find_mysql_socket")
    @patch("kanban_mcp.setup.get_migration_files")
    @patch("kanban_mcp.setup.mysql.connector")
    def test_no_socket_on_remote_host(
        self, mock_mysql, mock_get_files, mock_find_sock,
    ):
        from kanban_mcp.setup import _run_migrations

        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "001_initial_schema.sql"
            f1.write_text("CREATE TABLE items (id INT);")
            mock_get_files.return_value = [f1]

            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_mysql.connect.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchone.return_value = None
            mock_cursor.fetchall.return_value = []

            config = {
                "db_user": "kanban", "db_password": "pw",
                "db_host": "db.remote.com", "db_name": "kanban",
            }
            _run_migrations(config)

            mock_find_sock.assert_not_called()
            call_kwargs = mock_mysql.connect.call_args[1]
            self.assertNotIn("unix_socket", call_kwargs)
            self.assertEqual(
                call_kwargs["host"], "db.remote.com",
            )


class TestPrintAuthError(unittest.TestCase):
    """Test _print_auth_error produces correct messages."""

    def _make_error(self, errno):
        from mysql.connector import Error as RealMySQLError
        err = RealMySQLError("test error")
        err.errno = errno
        return err

    def _base_config(self):
        return {
            "db_name": "kanban", "db_user": "kanban",
            "db_password": "pw", "db_host": "localhost",
            "mysql_root_user": "root",
            "mysql_root_password": None,
        }

    def test_1698_socket_auth_message(self):
        from kanban_mcp.setup import _print_auth_error
        import io
        from contextlib import redirect_stdout

        err = self._make_error(1698)
        buf = io.StringIO()
        with redirect_stdout(buf):
            _print_auth_error(err, self._base_config())
        output = buf.getvalue()
        self.assertIn("auth_socket", output)
        self.assertIn("MYSQL_ROOT_PASSWORD", output)

    def test_1045_access_denied_message(self):
        from kanban_mcp.setup import _print_auth_error
        import io
        from contextlib import redirect_stdout

        err = self._make_error(1045)
        buf = io.StringIO()
        with redirect_stdout(buf):
            _print_auth_error(err, self._base_config())
        output = buf.getvalue()
        self.assertIn("Access denied", output)
        self.assertIn("MYSQL_ROOT_PASSWORD", output)

    def test_2002_connection_error_message(self):
        from kanban_mcp.setup import _print_auth_error
        import io
        from contextlib import redirect_stdout

        err = self._make_error(2002)
        buf = io.StringIO()
        with redirect_stdout(buf):
            _print_auth_error(err, self._base_config())
        output = buf.getvalue()
        self.assertIn("Cannot connect", output)
        self.assertIn("running", output)

    def test_2003_connection_error_message(self):
        from kanban_mcp.setup import _print_auth_error
        import io
        from contextlib import redirect_stdout

        err = self._make_error(2003)
        buf = io.StringIO()
        with redirect_stdout(buf):
            _print_auth_error(err, self._base_config())
        output = buf.getvalue()
        self.assertIn("Cannot connect", output)

    def test_unknown_error_includes_original(self):
        from kanban_mcp.setup import _print_auth_error
        import io
        from contextlib import redirect_stdout

        err = self._make_error(9999)
        buf = io.StringIO()
        with redirect_stdout(buf):
            _print_auth_error(err, self._base_config())
        output = buf.getvalue()
        self.assertIn("Could not connect", output)
        self.assertIn("MYSQL_ROOT_PASSWORD", output)


class TestCreateDatabaseFallbackChain(unittest.TestCase):
    """Test _create_database socket-to-TCP fallback logic."""

    def _base_config(self):
        return {
            "db_name": "kanban", "db_user": "kanban",
            "db_password": "pw", "db_host": "localhost",
            "mysql_root_user": "root",
            "mysql_root_password": None,
        }

    @patch("kanban_mcp.setup._find_mysql_socket")
    @patch("kanban_mcp.setup.mysql.connector")
    def test_tcp_fallback_on_socket_1698(
        self, mock_mysql, mock_find_sock,
    ):
        """When socket auth fails with 1698, tries TCP."""
        from kanban_mcp.setup import _create_database
        from mysql.connector import Error as RealMySQLError

        mock_find_sock.return_value = (
            "/var/run/mysqld/mysqld.sock"
        )

        socket_err = RealMySQLError("socket auth failed")
        socket_err.errno = 1698

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = MagicMock()
        # First call (socket) fails, second (TCP) succeeds
        mock_mysql.connect.side_effect = [
            socket_err, mock_conn,
        ]

        _create_database(self._base_config())

        # Should have tried twice
        self.assertEqual(mock_mysql.connect.call_count, 2)
        # Second call should use TCP (host, no unix_socket)
        tcp_call = mock_mysql.connect.call_args_list[1]
        tcp_args = tcp_call[1]
        self.assertIn("host", tcp_args)
        self.assertNotIn("unix_socket", tcp_args)
        self.assertEqual(tcp_args["password"], "")

    @patch("kanban_mcp.setup._find_mysql_socket")
    @patch("kanban_mcp.setup.mysql.connector")
    def test_tcp_fallback_on_socket_1045(
        self, mock_mysql, mock_find_sock,
    ):
        """When socket auth fails with 1045, tries TCP."""
        from kanban_mcp.setup import _create_database
        from mysql.connector import Error as RealMySQLError

        mock_find_sock.return_value = (
            "/var/run/mysqld/mysqld.sock"
        )

        socket_err = RealMySQLError("access denied")
        socket_err.errno = 1045

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = MagicMock()
        mock_mysql.connect.side_effect = [
            socket_err, mock_conn,
        ]

        _create_database(self._base_config())
        self.assertEqual(mock_mysql.connect.call_count, 2)

    @patch("kanban_mcp.setup._find_mysql_socket")
    @patch("kanban_mcp.setup.mysql.connector")
    def test_both_fail_exits_with_guidance(
        self, mock_mysql, mock_find_sock,
    ):
        """When both socket and TCP fail, exits with message."""
        from kanban_mcp.setup import _create_database
        from mysql.connector import Error as RealMySQLError

        mock_find_sock.return_value = (
            "/var/run/mysqld/mysqld.sock"
        )

        socket_err = RealMySQLError("socket auth failed")
        socket_err.errno = 1698
        tcp_err = RealMySQLError("tcp also failed")
        tcp_err.errno = 1045

        mock_mysql.connect.side_effect = [
            socket_err, tcp_err,
        ]

        with self.assertRaises(SystemExit):
            _create_database(self._base_config())

    @patch("kanban_mcp.setup._find_mysql_socket")
    @patch("kanban_mcp.setup.mysql.connector")
    def test_no_fallback_with_password(
        self, mock_mysql, mock_find_sock,
    ):
        """When password is provided, no fallback chain."""
        from kanban_mcp.setup import _create_database
        from mysql.connector import Error as RealMySQLError

        config = self._base_config()
        config["mysql_root_password"] = "rootpw"

        err = RealMySQLError("access denied")
        err.errno = 1045
        mock_mysql.connect.side_effect = err

        with self.assertRaises(SystemExit):
            _create_database(config)

        # Should only try once (no fallback)
        self.assertEqual(mock_mysql.connect.call_count, 1)

    @patch("kanban_mcp.setup._find_mysql_socket")
    @patch("kanban_mcp.setup.mysql.connector")
    def test_no_fallback_on_remote_host(
        self, mock_mysql, mock_find_sock,
    ):
        """When host is remote, no fallback chain."""
        from kanban_mcp.setup import _create_database
        from mysql.connector import Error as RealMySQLError

        config = self._base_config()
        config["db_host"] = "db.remote.com"

        err = RealMySQLError("connection failed")
        err.errno = 2003
        mock_mysql.connect.side_effect = err

        with self.assertRaises(SystemExit):
            _create_database(config)

        self.assertEqual(mock_mysql.connect.call_count, 1)

    @patch("kanban_mcp.setup._find_mysql_socket")
    @patch("kanban_mcp.setup.mysql.connector")
    def test_no_fallback_on_non_auth_error(
        self, mock_mysql, mock_find_sock,
    ):
        """Non-auth errors (e.g. 2002) skip the fallback."""
        from kanban_mcp.setup import _create_database
        from mysql.connector import Error as RealMySQLError

        mock_find_sock.return_value = (
            "/var/run/mysqld/mysqld.sock"
        )

        err = RealMySQLError("cannot connect")
        err.errno = 2002
        mock_mysql.connect.side_effect = err

        with self.assertRaises(SystemExit):
            _create_database(self._base_config())

        # Only one attempt — 2002 is not an auth error
        self.assertEqual(mock_mysql.connect.call_count, 1)


class TestRunMigrationsConnectionError(unittest.TestCase):
    """Test _run_migrations handles connection failures."""

    @patch("kanban_mcp.setup._find_mysql_socket")
    @patch("kanban_mcp.setup.get_migration_files")
    @patch("kanban_mcp.setup.mysql.connector")
    def test_connection_failure_exits_with_message(
        self, mock_mysql, mock_get_files, mock_find_sock,
    ):
        from kanban_mcp.setup import _run_migrations
        from mysql.connector import Error as RealMySQLError
        import io
        from contextlib import redirect_stdout

        mock_find_sock.return_value = (
            "/var/run/mysqld/mysqld.sock"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "001_initial_schema.sql"
            f1.write_text("CREATE TABLE items (id INT);")
            mock_get_files.return_value = [f1]

            err = RealMySQLError("Access denied")
            err.errno = 1045
            mock_mysql.connect.side_effect = err

            config = {
                "db_user": "kanban", "db_password": "pw",
                "db_host": "localhost", "db_name": "kanban",
            }

            buf = io.StringIO()
            with self.assertRaises(SystemExit), \
                    redirect_stdout(buf):
                _run_migrations(config)

            output = buf.getvalue()
            self.assertIn("Could not connect", output)
            self.assertIn("kanban", output)
            self.assertIn(".env", output)


class TestCreateDatabasePasswordEscaping(unittest.TestCase):
    """Test _create_database escapes single quotes in passwords."""

    @patch("kanban_mcp.setup._find_mysql_socket")
    @patch("kanban_mcp.setup.mysql.connector")
    def test_single_quote_in_password_escaped(
        self, mock_mysql, mock_find_sock,
    ):
        from kanban_mcp.setup import _create_database
        mock_find_sock.return_value = None
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_mysql.connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        config = {
            "db_name": "kanban", "db_user": "kanban",
            "db_password": "pass'word",
            "db_host": "localhost",
            "mysql_root_user": "root",
            "mysql_root_password": "rootpw",
        }
        _create_database(config)

        executed = [
            str(c) for c in mock_cursor.execute.call_args_list
        ]
        all_sql = " ".join(executed)
        # The single quote must be escaped as ''
        self.assertIn("pass''word", all_sql)
        # Must NOT contain the unescaped version in SQL
        # (the raw "pass'word" would break the SQL string)
        # Check CREATE USER uses escaped form
        for call in mock_cursor.execute.call_args_list:
            sql = call[0][0]
            if "CREATE USER" in sql:
                self.assertIn("pass''word", sql)
            if "ALTER USER" in sql:
                self.assertIn("pass''word", sql)


class TestCreateDatabaseTcpFallbackReportsCorrectError(
    unittest.TestCase,
):
    """Test TCP fallback reports the TCP error, not socket error."""

    @patch("kanban_mcp.setup._find_mysql_socket")
    @patch("kanban_mcp.setup.mysql.connector")
    def test_reports_tcp_error_not_socket_error(
        self, mock_mysql, mock_find_sock,
    ):
        from kanban_mcp.setup import _create_database
        from mysql.connector import Error as RealMySQLError
        import io
        from contextlib import redirect_stdout

        mock_find_sock.return_value = (
            "/var/run/mysqld/mysqld.sock"
        )

        socket_err = RealMySQLError("socket auth failed")
        socket_err.errno = 1698

        tcp_err = RealMySQLError("tcp access denied")
        tcp_err.errno = 1045

        mock_mysql.connect.side_effect = [
            socket_err, tcp_err,
        ]

        config = {
            "db_name": "kanban", "db_user": "kanban",
            "db_password": "pw", "db_host": "localhost",
            "mysql_root_user": "root",
            "mysql_root_password": None,
        }

        buf = io.StringIO()
        with self.assertRaises(SystemExit), \
                redirect_stdout(buf):
            _create_database(config)

        output = buf.getvalue()
        # Should report the TCP error (1045 = access denied)
        self.assertIn("Access denied", output)
        # Should NOT contain the socket error message
        self.assertNotIn("auth_socket", output)


class TestEnsureSchemaMigrationsTableCharset(unittest.TestCase):
    """Test schema_migrations table has ENGINE and charset."""

    def test_includes_engine_and_charset(self):
        from kanban_mcp.setup import (
            _ensure_schema_migrations_table,
        )
        mock_cursor = MagicMock()
        _ensure_schema_migrations_table(mock_cursor)
        sql = mock_cursor.execute.call_args[0][0]
        self.assertIn("ENGINE=InnoDB", sql)
        self.assertIn("utf8mb4_unicode_ci", sql)


class TestLoggingBeforeAutoMigrate(unittest.TestCase):
    """Test logging.basicConfig runs before auto_migrate."""

    @patch("kanban_mcp.setup.auto_migrate")
    @patch(
        "kanban_mcp.core.MySQLConnectionPool",
    )
    @patch.dict(os.environ, {
        "KANBAN_DB_USER": "test",
        "KANBAN_DB_PASSWORD": "test",
        "KANBAN_DB_NAME": "test",
    })
    def test_basicconfig_before_auto_migrate(
        self, mock_pool, mock_auto_migrate,
    ):
        """auto_migrate is called after logging.basicConfig."""
        from kanban_mcp.core import KanbanMCPServer
        import logging

        call_order = []

        original_basicConfig = logging.basicConfig

        def track_basicConfig(**kwargs):
            call_order.append("basicConfig")
            original_basicConfig(**kwargs)

        def track_auto_migrate(config):
            call_order.append("auto_migrate")

        mock_auto_migrate.side_effect = track_auto_migrate

        with patch(
            "logging.basicConfig",
            side_effect=track_basicConfig,
        ):
            KanbanMCPServer()

        self.assertIn("basicConfig", call_order)
        self.assertIn("auto_migrate", call_order)
        self.assertLess(
            call_order.index("basicConfig"),
            call_order.index("auto_migrate"),
            "logging.basicConfig must run before auto_migrate",
        )


class TestPortConfig(unittest.TestCase):
    """Test port resolution from env, CLI, and defaults."""

    def test_port_from_env(self):
        from kanban_mcp.setup import resolve_config, build_parser
        parser = build_parser()
        args = parser.parse_args(["--auto"])
        with patch.dict(
            os.environ,
            {"KANBAN_DB_PORT": "3307"},
            clear=False,
        ):
            config = resolve_config(args)
        self.assertEqual(config["db_port"], "3307")

    def test_port_default_3306(self):
        from kanban_mcp.setup import resolve_config, build_parser
        parser = build_parser()
        args = parser.parse_args(["--auto"])
        env_clear = {
            "KANBAN_DB_PORT": "",
        }
        with patch.dict(os.environ, env_clear, clear=False):
            os.environ.pop("KANBAN_DB_PORT", None)
            config = resolve_config(args)
        self.assertEqual(config["db_port"], "3306")

    def test_cli_overrides_env(self):
        from kanban_mcp.setup import resolve_config, build_parser
        parser = build_parser()
        args = parser.parse_args([
            "--auto", "--db-port", "3308",
        ])
        with patch.dict(
            os.environ,
            {"KANBAN_DB_PORT": "3307"},
            clear=False,
        ):
            config = resolve_config(args)
        self.assertEqual(config["db_port"], "3308")


class TestEnvFilePort(unittest.TestCase):
    """Test .env file writing includes port when non-default."""

    def test_port_included_when_non_default(self):
        from kanban_mcp.setup import write_env_file
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = os.path.join(tmpdir, ".env")
            write_env_file(
                env_path,
                db_host="localhost",
                db_user="kanban",
                db_password="secret",
                db_name="kanban",
                db_port="3307",
            )
            content = Path(env_path).read_text()
            self.assertIn("KANBAN_DB_PORT=3307", content)

    def test_port_omitted_when_default(self):
        from kanban_mcp.setup import write_env_file
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = os.path.join(tmpdir, ".env")
            write_env_file(
                env_path,
                db_host="localhost",
                db_user="kanban",
                db_password="secret",
                db_name="kanban",
                db_port="3306",
            )
            content = Path(env_path).read_text()
            self.assertNotIn("KANBAN_DB_PORT", content)


class TestKanbanDBPort(unittest.TestCase):
    """Test KanbanDB port handling."""

    @patch('kanban_mcp.core.MySQLConnectionPool')
    @patch.dict(os.environ, {
        'KANBAN_DB_USER': 'test',
        'KANBAN_DB_PASSWORD': 'test',
        'KANBAN_DB_NAME': 'test',
    })
    def test_port_from_env_var(self, mock_pool):
        from kanban_mcp.core import KanbanDB
        with patch.dict(
            os.environ,
            {"KANBAN_DB_PORT": "3307"},
            clear=False,
        ):
            db = KanbanDB()
        self.assertEqual(db.config["port"], 3307)

    @patch('kanban_mcp.core.MySQLConnectionPool')
    @patch.dict(os.environ, {
        'KANBAN_DB_USER': 'test',
        'KANBAN_DB_PASSWORD': 'test',
        'KANBAN_DB_NAME': 'test',
    })
    def test_port_default_3306(self, mock_pool):
        from kanban_mcp.core import KanbanDB
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("KANBAN_DB_PORT", None)
            db = KanbanDB()
        self.assertEqual(db.config["port"], 3306)

    @patch('kanban_mcp.core.MySQLConnectionPool')
    @patch.dict(os.environ, {
        'KANBAN_DB_USER': 'test',
        'KANBAN_DB_PASSWORD': 'test',
        'KANBAN_DB_NAME': 'test',
    })
    def test_port_constructor_param(self, mock_pool):
        from kanban_mcp.core import KanbanDB
        db = KanbanDB(port=3308)
        self.assertEqual(db.config["port"], 3308)

    @patch('kanban_mcp.core.MySQLConnectionPool')
    @patch.dict(os.environ, {
        'KANBAN_DB_USER': 'test',
        'KANBAN_DB_PASSWORD': 'test',
        'KANBAN_DB_NAME': 'test',
    })
    def test_port_passed_to_pool(self, mock_pool):
        from kanban_mcp.core import KanbanDB
        KanbanDB(port=3307)
        call_kwargs = mock_pool.call_args[1]
        self.assertEqual(call_kwargs["port"], 3307)


class TestMcpConfigPort(unittest.TestCase):
    """Test mcp_config_json includes port when non-default."""

    def test_port_included_when_non_default(self):
        import json
        from kanban_mcp.setup import mcp_config_json
        result = mcp_config_json(
            "localhost", "kanban", "pw", "kanban",
            db_port="3307",
        )
        parsed = json.loads(result)
        env = parsed["mcpServers"]["kanban"]["env"]
        self.assertEqual(env["KANBAN_DB_PORT"], "3307")

    def test_port_omitted_when_default(self):
        import json
        from kanban_mcp.setup import mcp_config_json
        result = mcp_config_json(
            "localhost", "kanban", "pw", "kanban",
            db_port="3306",
        )
        parsed = json.loads(result)
        env = parsed["mcpServers"]["kanban"]["env"]
        self.assertNotIn("KANBAN_DB_PORT", env)


class TestWebPortEnvVar(unittest.TestCase):
    """Test kanban-web reads KANBAN_WEB_PORT env var."""

    def _run_main_and_capture_port(self, cli_args=None):
        """Run web main() with mocked app.run, return the port used."""
        captured = {}

        def fake_run(**kwargs):
            captured.update(kwargs)

        with patch("kanban_mcp.web.app") as mock_app:
            mock_app.run = fake_run
            # Force debug mode so it uses app.run, not gunicorn
            with patch(
                "sys.argv",
                ["kanban-web", "--debug"]
                + (cli_args or []),
            ):
                from kanban_mcp.web import main
                main()
        return captured.get("port")

    def test_port_from_env(self):
        with patch.dict(
            os.environ,
            {"KANBAN_WEB_PORT": "8080"},
            clear=False,
        ):
            port = self._run_main_and_capture_port()
            self.assertEqual(port, 8080)

    def test_port_default_5000(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("KANBAN_WEB_PORT", None)
            port = self._run_main_and_capture_port()
            self.assertEqual(port, 5000)

    def test_cli_overrides_env(self):
        with patch.dict(
            os.environ,
            {"KANBAN_WEB_PORT": "8080"},
            clear=False,
        ):
            port = self._run_main_and_capture_port(
                ["--port", "9090"],
            )
            self.assertEqual(port, 9090)


if __name__ == "__main__":
    unittest.main()
