"""Tests for issues found during v0.2.0 code review.

Covers:
- #1  Thread-safety of SQLiteBackend.db_cursor (row_factory race)
- #8  LIKE wildcard escaping in SQLite search_fulltext
- #3  Backtick removal verification (vector column queries)
- #4  Migration error handling symmetry (SQLite table-absent skip)
- #9  auto_migrate re-raises on fatal errors
- #11 _split_sql handling of BEGIN TRANSACTION vs BEGIN...END triggers
"""

import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from kanban_mcp.db.sqlite_backend import SQLiteBackend


class TestThreadSafeDbCursor(unittest.TestCase):
    """#1: db_cursor must not mutate shared connection state."""

    def setUp(self):
        # Use file-based DB for real multi-thread concurrency (WAL mode)
        self._tmpfile = tempfile.NamedTemporaryFile(
            suffix='.db', delete=False)
        self._tmpfile.close()
        self.backend = SQLiteBackend(db_path=self._tmpfile.name)
        with self.backend.db_cursor(commit=True) as c:
            c.execute("CREATE TABLE t (id INTEGER, name TEXT)")
            c.execute("INSERT INTO t VALUES (1, 'alice')")
            c.execute("INSERT INTO t VALUES (2, 'bob')")

    def tearDown(self):
        os.unlink(self._tmpfile.name)

    def test_dict_cursor_without_row_factory(self):
        """Dictionary mode should work without setting row_factory."""
        with self.backend.db_cursor(dictionary=True) as c:
            c.execute("SELECT * FROM t WHERE id = 1")
            row = c.fetchone()
        self.assertIsInstance(row, dict)
        self.assertEqual(row['name'], 'alice')

    def test_plain_cursor_returns_tuples(self):
        """Non-dictionary mode should return plain tuples."""
        with self.backend.db_cursor() as c:
            c.execute("SELECT * FROM t WHERE id = 1")
            row = c.fetchone()
        self.assertIsInstance(row, tuple)
        self.assertEqual(row[1], 'alice')

    def test_concurrent_dict_and_plain_cursors(self):
        """Concurrent dict and plain cursors must not interfere."""
        errors = []
        barrier = threading.Barrier(2, timeout=5)

        def dict_worker():
            try:
                barrier.wait()
                for _ in range(50):
                    with self.backend.db_cursor(dictionary=True) as c:
                        c.execute("SELECT * FROM t")
                        rows = c.fetchall()
                        for row in rows:
                            if not isinstance(row, dict):
                                errors.append(
                                    f"dict cursor got {type(row)}")
                                return
                            _ = row['name']  # must not KeyError
            except Exception as e:
                errors.append(str(e))

        def plain_worker():
            try:
                barrier.wait()
                for _ in range(50):
                    with self.backend.db_cursor() as c:
                        c.execute("SELECT * FROM t")
                        rows = c.fetchall()
                        for row in rows:
                            if not isinstance(row, tuple):
                                errors.append(
                                    f"plain cursor got {type(row)}")
                                return
                            _ = row[1]  # must not IndexError
            except Exception as e:
                errors.append(str(e))

        t1 = threading.Thread(target=dict_worker)
        t2 = threading.Thread(target=plain_worker)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)
        self.assertEqual(errors, [],
                         f"Thread-safety errors: {errors}")

    def test_fetchall_returns_dicts(self):
        """fetchall in dictionary mode returns list of dicts."""
        with self.backend.db_cursor(dictionary=True) as c:
            c.execute("SELECT * FROM t ORDER BY id")
            rows = c.fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['id'], 1)
        self.assertEqual(rows[1]['name'], 'bob')

    def test_fetchone_none(self):
        """fetchone returns None for empty result in dict mode."""
        with self.backend.db_cursor(dictionary=True) as c:
            c.execute("SELECT * FROM t WHERE id = 999")
            row = c.fetchone()
        self.assertIsNone(row)


class TestLikeWildcardEscape(unittest.TestCase):
    """#8: search_fulltext must escape % and _ in user queries."""

    def setUp(self):
        self.backend = SQLiteBackend(db_path=':memory:')
        # Bootstrap schema
        from kanban_mcp.setup import auto_migrate
        auto_migrate(self.backend)
        # Insert test data
        with self.backend.db_cursor(commit=True) as c:
            c.execute(
                "INSERT INTO projects (id, directory_path, name) "
                "VALUES ('p1', '/test', 'test')")
            # Get type and status IDs
            c.execute("SELECT id FROM item_types WHERE name = 'issue'")
            type_id = c.fetchone()[0]
            c.execute("SELECT id FROM statuses WHERE name = 'backlog'")
            status_id = c.fetchone()[0]
            # Item with literal % in title
            c.execute(
                "INSERT INTO items "
                "(project_id, type_id, status_id, title, description) "
                "VALUES ('p1', ?, ?, '50% off sale', 'a]discount')",
                (type_id, status_id))
            # Item that should NOT match "50% off"
            c.execute(
                "INSERT INTO items "
                "(project_id, type_id, status_id, title, description) "
                "VALUES ('p1', ?, ?, '500 offers', 'many offers')",
                (type_id, status_id))
            # Item with literal _ in title
            c.execute(
                "INSERT INTO items "
                "(project_id, type_id, status_id, title, description) "
                "VALUES ('p1', ?, ?, 'snake_case naming', 'style guide')",
                (type_id, status_id))

    def test_percent_in_query_is_literal(self):
        """Searching for '50% off' should match literally, not as wildcard."""
        result = self.backend.search_fulltext('p1', '50% off', 10)
        titles = [item['title'] for item in result['items']]
        self.assertIn('50% off sale', titles)
        self.assertNotIn('500 offers', titles)

    def test_underscore_in_query_is_literal(self):
        """Searching for 'snake_case' should match literally."""
        result = self.backend.search_fulltext('p1', 'snake_case', 10)
        titles = [item['title'] for item in result['items']]
        self.assertIn('snake_case naming', titles)

    def test_backslash_in_query_is_literal(self):
        """Backslash in query should not break the LIKE escape."""
        # Should not raise, even with backslash
        result = self.backend.search_fulltext('p1', 'path\\to', 10)
        self.assertIsInstance(result, dict)


class TestBacktickRemoval(unittest.TestCase):
    """#3: core.py should not use MySQL backtick quoting."""

    def test_no_backtick_vector_in_core(self):
        """The vector column should not be backtick-quoted."""
        core_path = Path(__file__).parent.parent / 'kanban_mcp' / 'core.py'
        content = core_path.read_text()
        self.assertNotIn('`vector`', content,
                         "Found MySQL backtick quoting on 'vector' column")


class TestSplitSqlBeginTransaction(unittest.TestCase):
    """#11: _split_sql must not confuse BEGIN TRANSACTION with triggers."""

    def test_begin_transaction_not_treated_as_block(self):
        from kanban_mcp.setup import _split_sql
        sql = (
            "BEGIN TRANSACTION;\n"
            "INSERT INTO t VALUES (1);\n"
            "INSERT INTO t VALUES (2);\n"
            "COMMIT;\n"
        )
        stmts = _split_sql(sql)
        # Should produce 4 separate statements, not merge them
        self.assertEqual(len(stmts), 4)
        self.assertTrue(stmts[0].upper().startswith('BEGIN'))
        self.assertTrue(stmts[-1].upper().startswith('COMMIT'))

    def test_begin_immediate_not_treated_as_block(self):
        from kanban_mcp.setup import _split_sql
        sql = "BEGIN IMMEDIATE; INSERT INTO t VALUES (1); COMMIT;"
        stmts = _split_sql(sql)
        self.assertEqual(len(stmts), 3)

    def test_begin_deferred_not_treated_as_block(self):
        from kanban_mcp.setup import _split_sql
        sql = "BEGIN DEFERRED; INSERT INTO t VALUES (1); COMMIT;"
        stmts = _split_sql(sql)
        self.assertEqual(len(stmts), 3)

    def test_begin_exclusive_not_treated_as_block(self):
        from kanban_mcp.setup import _split_sql
        sql = "BEGIN EXCLUSIVE; INSERT INTO t VALUES (1); COMMIT;"
        stmts = _split_sql(sql)
        self.assertEqual(len(stmts), 3)

    def test_trigger_begin_end_still_works(self):
        from kanban_mcp.setup import _split_sql
        sql = (
            "CREATE TRIGGER test_trigger AFTER INSERT ON t\n"
            "BEGIN\n"
            "  INSERT INTO log VALUES (NEW.id);\n"
            "END;\n"
            "INSERT INTO t VALUES (1);\n"
        )
        stmts = _split_sql(sql)
        # Should produce 2: the CREATE TRIGGER (with BEGIN...END) and INSERT
        self.assertEqual(len(stmts), 2)
        self.assertIn('BEGIN', stmts[0])
        self.assertIn('END', stmts[0])


class TestMigrationTableAbsentHandling(unittest.TestCase):
    """#4: Migration should handle table-absent errors on both backends."""

    def test_sqlite_no_such_table_is_skipped(self):
        """SQLite 'no such table' errors should be skipped like MySQL 1146."""
        from kanban_mcp.setup import _auto_migrate_backend
        import logging

        backend = SQLiteBackend(db_path=':memory:')
        log = logging.getLogger('test_migration')

        # Create schema_migrations table
        with backend.db_cursor(commit=True) as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename TEXT PRIMARY KEY,
                    applied_at TEXT DEFAULT (datetime('now'))
                )
            """)

        # Create a migration that references a non-existent table
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            mig = Path(tmpdir) / '001_test.sql'
            mig.write_text(
                "CREATE TABLE IF NOT EXISTS real_table (id INTEGER);\n"
                "INSERT INTO nonexistent_table VALUES (1);\n"
                "INSERT INTO real_table VALUES (42);\n"
            )
            with patch(
                'kanban_mcp.setup.find_migrations_dir',
                return_value=tmpdir,
            ):
                # Should not raise — the table-absent error is skipped
                _auto_migrate_backend(backend, log)

        # The migration should be marked as applied (with warning)
        with backend.db_cursor() as c:
            c.execute("SELECT filename FROM schema_migrations")
            applied = [r[0] for r in c.fetchall()]
        self.assertIn('001_test.sql', applied)

        # The valid statements should have been executed
        with backend.db_cursor() as c:
            c.execute("SELECT * FROM real_table")
            rows = c.fetchall()
        self.assertEqual(len(rows), 1)


class TestAutoMigrateReraises(unittest.TestCase):
    """#9: auto_migrate must re-raise fatal errors, not swallow them."""

    def test_fatal_error_propagates(self):
        from kanban_mcp.setup import _auto_migrate_backend
        import logging

        backend = MagicMock()
        backend.backend_type = 'sqlite'
        # Make db_cursor raise on first call (schema_migrations creation)
        backend.db_cursor.side_effect = PermissionError("disk full")

        log = logging.getLogger('test_reraise')

        with patch(
            'kanban_mcp.setup.find_migrations_dir',
            return_value='/fake/path',
        ):
            with patch(
                'kanban_mcp.setup.Path.glob',
                return_value=[Path('/fake/001.sql')],
            ):
                with self.assertRaises(PermissionError):
                    _auto_migrate_backend(backend, log)


class TestWriteSqliteEnvFile(unittest.TestCase):
    """write_sqlite_env_file must include KANBAN_SQLITE_PATH when given."""

    def test_custom_path_written_to_env(self):
        """A custom sqlite_path must appear in the .env file."""
        from kanban_mcp.setup import write_sqlite_env_file
        with tempfile.NamedTemporaryFile(
                mode='w', suffix='.env', delete=False) as f:
            env_path = f.name
        try:
            write_sqlite_env_file(env_path, '/custom/kanban.db')
            content = Path(env_path).read_text()
            self.assertIn(
                'KANBAN_SQLITE_PATH=/custom/kanban.db', content)
        finally:
            os.unlink(env_path)

    def test_default_path_omits_sqlite_path(self):
        """When no custom path, KANBAN_SQLITE_PATH should be absent."""
        from kanban_mcp.setup import write_sqlite_env_file
        with tempfile.NamedTemporaryFile(
                mode='w', suffix='.env', delete=False) as f:
            env_path = f.name
        try:
            write_sqlite_env_file(env_path, None)
            content = Path(env_path).read_text()
            self.assertNotIn('KANBAN_SQLITE_PATH', content)
            self.assertIn('KANBAN_BACKEND=sqlite', content)
        finally:
            os.unlink(env_path)


class TestCliMigrationSkipsNoSuchTable(unittest.TestCase):
    """_run_migrations_with_backend must skip 'no such table' on SQLite."""

    def test_sqlite_no_such_table_skipped_in_cli(self):
        """CLI migration path should skip SQLite table-absent errors."""
        from kanban_mcp.setup import _run_migrations_with_backend
        backend = SQLiteBackend(db_path=':memory:')

        # Bootstrap schema
        from kanban_mcp.setup import auto_migrate
        auto_migrate(backend)

        # Create a migration that hits a non-existent table
        with tempfile.TemporaryDirectory() as tmpdir:
            mig = Path(tmpdir) / '002_test.sql'
            mig.write_text(
                "CREATE TABLE IF NOT EXISTS cli_test (id INTEGER);\n"
                "INSERT INTO nonexistent_cli_table VALUES (1);\n"
                "INSERT INTO cli_test VALUES (42);\n"
            )
            with patch(
                'kanban_mcp.setup.find_migrations_dir',
                return_value=tmpdir,
            ):
                # Should not sys.exit — the table-absent error is skipped
                _run_migrations_with_backend(backend)

        # The valid statements should have been executed
        with backend.db_cursor() as c:
            c.execute("SELECT * FROM cli_test")
            rows = c.fetchall()
        self.assertEqual(len(rows), 1)


if __name__ == '__main__':
    unittest.main()
