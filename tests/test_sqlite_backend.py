#!/usr/bin/env python3
"""
SQLite-specific backend tests.

Tests path resolution, PRAGMAs, connection handling — things
unique to SQLite. Backend-agnostic contract tests are in
test_db_backend.py and test_integration.py.
"""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from kanban_mcp.db.sqlite_backend import SQLiteBackend


class TestSQLitePathResolution(unittest.TestCase):
    """Tests for SQLite database path resolution."""

    def test_default_path_xdg_compliant(self):
        """Default path should use XDG_DATA_HOME."""
        with patch.dict(os.environ, {
            'XDG_DATA_HOME': '/tmp/xdg_test_data'
        }, clear=False):
            # Remove overrides
            env = os.environ.copy()
            env.pop('KANBAN_SQLITE_PATH', None)
            with patch.dict(os.environ, env, clear=True):
                os.environ['XDG_DATA_HOME'] = '/tmp/xdg_test_data'
                backend = SQLiteBackend()
        expected = str(
            Path('/tmp/xdg_test_data') / 'kanban-mcp' / 'kanban.db')
        self.assertEqual(backend._db_path, expected)

    def test_custom_path_from_env(self):
        """KANBAN_SQLITE_PATH should override default."""
        with patch.dict(os.environ, {
            'KANBAN_SQLITE_PATH': '/tmp/custom_kanban.db'
        }):
            backend = SQLiteBackend()
        self.assertEqual(backend._db_path, '/tmp/custom_kanban.db')

    def test_custom_path_from_constructor(self):
        """db_path= arg should override env."""
        with patch.dict(os.environ, {
            'KANBAN_SQLITE_PATH': '/tmp/env_path.db'
        }):
            backend = SQLiteBackend(db_path='/tmp/arg_path.db')
        self.assertEqual(backend._db_path, '/tmp/arg_path.db')

    def test_memory_database(self):
        """:memory: should work as a database path."""
        backend = SQLiteBackend(db_path=':memory:')
        self.assertEqual(backend._db_path, ':memory:')
        # Verify we can actually use it
        with backend.db_cursor(commit=True) as cursor:
            cursor.execute(
                "CREATE TABLE test (id INTEGER PRIMARY KEY)")
            cursor.execute("INSERT INTO test VALUES (1)")
        with backend.db_cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM test")
            rows = cursor.fetchall()
        self.assertEqual(len(rows), 1)

    def test_auto_creates_parent_directory(self):
        """Should create parent directories if they don't exist."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            deep_path = os.path.join(
                tmp, 'a', 'b', 'c', 'kanban.db')
            backend = SQLiteBackend(db_path=deep_path)  # noqa: F841
            self.assertTrue(
                os.path.isdir(os.path.join(tmp, 'a', 'b', 'c')))

    def test_path_with_spaces(self):
        """Should handle paths containing spaces."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'my project', 'kanban.db')
            backend = SQLiteBackend(db_path=path)
            with backend.db_cursor(commit=True) as cursor:
                cursor.execute(
                    "CREATE TABLE test (id INTEGER PRIMARY KEY)")
            self.assertTrue(os.path.exists(path))

    def test_path_with_unicode(self):
        """Should handle unicode directory names."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, '日本語', 'kanban.db')
            backend = SQLiteBackend(db_path=path)
            with backend.db_cursor(commit=True) as cursor:
                cursor.execute(
                    "CREATE TABLE test (id INTEGER PRIMARY KEY)")
            self.assertTrue(os.path.exists(path))

    def test_nonexistent_deep_path(self):
        """Should create nested parent dirs."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(
                tmp, 'x', 'y', 'z', 'w', 'kanban.db')
            backend = SQLiteBackend(db_path=path)  # noqa: F841
            self.assertTrue(os.path.isdir(
                os.path.join(tmp, 'x', 'y', 'z', 'w')))


class TestSQLitePragmas(unittest.TestCase):
    """Tests for SQLite PRAGMA settings."""

    def test_wal_mode_enabled(self):
        """File-based db should have journal_mode=wal."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'test.db')
            backend = SQLiteBackend(db_path=path)
            with backend.db_cursor() as cursor:
                cursor.execute('PRAGMA journal_mode')
                mode = cursor.fetchone()[0]
            self.assertEqual(mode, 'wal')

    def test_memory_skips_wal(self):
        """:memory: doesn't use WAL (it uses 'memory' journal mode)."""
        backend = SQLiteBackend(db_path=':memory:')
        with backend.db_cursor() as cursor:
            cursor.execute('PRAGMA journal_mode')
            mode = cursor.fetchone()[0]
        self.assertEqual(mode, 'memory')

    def test_busy_timeout_set(self):
        """PRAGMA busy_timeout should be 5000."""
        backend = SQLiteBackend(db_path=':memory:')
        with backend.db_cursor() as cursor:
            cursor.execute('PRAGMA busy_timeout')
            timeout = cursor.fetchone()[0]
        self.assertEqual(timeout, 5000)

    def test_foreign_keys_enabled(self):
        """PRAGMA foreign_keys should be 1 (ON)."""
        backend = SQLiteBackend(db_path=':memory:')
        with backend.db_cursor() as cursor:
            cursor.execute('PRAGMA foreign_keys')
            fk = cursor.fetchone()[0]
        self.assertEqual(fk, 1)


class TestSQLiteBackendContract(unittest.TestCase):
    """SQLite backend contract tests (parallel to TestMySQLBackend)."""

    def test_placeholder_is_question_mark(self):
        backend = SQLiteBackend(db_path=':memory:')
        self.assertEqual(backend.placeholder, '?')

    def test_insert_ignore_is_or_ignore(self):
        backend = SQLiteBackend(db_path=':memory:')
        self.assertEqual(backend.insert_ignore, 'INSERT OR IGNORE')

    def test_backend_type_is_sqlite(self):
        backend = SQLiteBackend(db_path=':memory:')
        self.assertEqual(backend.backend_type, 'sqlite')

    def test_now_func(self):
        backend = SQLiteBackend(db_path=':memory:')
        self.assertEqual(backend.now_func, "datetime('now')")

    def test_is_duplicate_error(self):
        backend = SQLiteBackend(db_path=':memory:')
        exc = Exception('UNIQUE constraint failed: tags.project_id, tags.name')
        self.assertTrue(backend.is_duplicate_error(exc))
        exc2 = Exception('no such table: items')
        self.assertFalse(backend.is_duplicate_error(exc2))

    def test_is_subclass_of_database_backend(self):
        from kanban_mcp.db.base import DatabaseBackend
        self.assertTrue(issubclass(SQLiteBackend, DatabaseBackend))

    def test_config_returns_database_path(self):
        backend = SQLiteBackend(db_path=':memory:')
        self.assertEqual(backend.config, {'database': ':memory:'})


class TestSQLiteCursorModes(unittest.TestCase):
    """Test cursor dictionary and commit modes."""

    def setUp(self):
        self.backend = SQLiteBackend(db_path=':memory:')
        with self.backend.db_cursor(commit=True) as cursor:
            cursor.execute(
                "CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
            cursor.execute(
                "INSERT INTO test VALUES (1, 'alice')")
            cursor.execute(
                "INSERT INTO test VALUES (2, 'bob')")

    def test_dictionary_mode_returns_dicts(self):
        """dictionary=True should return real dict objects."""
        with self.backend.db_cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM test WHERE id = 1")
            row = cursor.fetchone()
        self.assertIsInstance(row, dict)
        self.assertEqual(row['id'], 1)
        self.assertEqual(row['name'], 'alice')

    def test_dictionary_mode_fetchall(self):
        with self.backend.db_cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM test ORDER BY id")
            rows = cursor.fetchall()
        self.assertEqual(len(rows), 2)
        self.assertIsInstance(rows[0], dict)
        self.assertEqual(rows[0]['id'], 1)
        self.assertEqual(rows[1]['name'], 'bob')

    def test_non_dictionary_mode_returns_tuples(self):
        with self.backend.db_cursor(dictionary=False) as cursor:
            cursor.execute("SELECT * FROM test WHERE id = 1")
            row = cursor.fetchone()
        self.assertIsInstance(row, tuple)

    def test_commit_mode_persists(self):
        with self.backend.db_cursor(commit=True) as cursor:
            cursor.execute(
                "INSERT INTO test VALUES (3, 'charlie')")
        with self.backend.db_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM test")
            count = cursor.fetchone()[0]
        self.assertEqual(count, 3)

    def test_rollback_on_error(self):
        try:
            with self.backend.db_cursor(commit=True) as cursor:
                cursor.execute(
                    "INSERT INTO test VALUES (3, 'charlie')")
                raise RuntimeError("test error")
        except RuntimeError:
            pass
        with self.backend.db_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM test")
            count = cursor.fetchone()[0]
        self.assertEqual(count, 2)

    def test_fetchone_returns_none_for_empty(self):
        with self.backend.db_cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM test WHERE id = 999")
            row = cursor.fetchone()
        self.assertIsNone(row)


if __name__ == "__main__":
    unittest.main()
