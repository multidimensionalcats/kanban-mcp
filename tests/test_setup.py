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


if __name__ == "__main__":
    unittest.main()
