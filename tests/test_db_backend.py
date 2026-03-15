#!/usr/bin/env python3
"""
Tests for the pluggable database backend abstraction.

RED phase: These tests define the contract for DatabaseBackend,
MySQLBackend, create_backend() factory, and KanbanDB._sql() helper.
All tests should FAIL until implementation is written.
"""

import os
import unittest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Backend interface tests
# ---------------------------------------------------------------------------

class TestBackendInterface(unittest.TestCase):
    """Tests that any DatabaseBackend implementation must satisfy."""

    def test_backend_has_required_properties(self):
        """Backend must expose placeholder, insert_ignore, backend_type."""
        from kanban_mcp.db.mysql_backend import MySQLBackend
        with patch('kanban_mcp.db.mysql_backend.MySQLConnectionPool'):
            with patch.dict(os.environ, {
                'KANBAN_DB_USER': 'test',
                'KANBAN_DB_PASSWORD': 'test',
                'KANBAN_DB_NAME': 'test',
            }):
                backend = MySQLBackend()
        self.assertTrue(hasattr(backend, 'placeholder'))
        self.assertTrue(hasattr(backend, 'insert_ignore'))
        self.assertTrue(hasattr(backend, 'backend_type'))

    def test_placeholder_is_valid(self):
        """placeholder must be '%s' or '?'."""
        from kanban_mcp.db.mysql_backend import MySQLBackend
        with patch('kanban_mcp.db.mysql_backend.MySQLConnectionPool'):
            with patch.dict(os.environ, {
                'KANBAN_DB_USER': 'test',
                'KANBAN_DB_PASSWORD': 'test',
                'KANBAN_DB_NAME': 'test',
            }):
                backend = MySQLBackend()
        self.assertIn(backend.placeholder, ('%s', '?'))

    def test_insert_ignore_is_valid(self):
        """insert_ignore must be 'INSERT IGNORE' or 'INSERT OR IGNORE'."""
        from kanban_mcp.db.mysql_backend import MySQLBackend
        with patch('kanban_mcp.db.mysql_backend.MySQLConnectionPool'):
            with patch.dict(os.environ, {
                'KANBAN_DB_USER': 'test',
                'KANBAN_DB_PASSWORD': 'test',
                'KANBAN_DB_NAME': 'test',
            }):
                backend = MySQLBackend()
        self.assertIn(backend.insert_ignore,
                      ('INSERT IGNORE', 'INSERT OR IGNORE'))

    def test_backend_type_is_valid(self):
        """backend_type must be 'mysql' or 'sqlite'."""
        from kanban_mcp.db.mysql_backend import MySQLBackend
        with patch('kanban_mcp.db.mysql_backend.MySQLConnectionPool'):
            with patch.dict(os.environ, {
                'KANBAN_DB_USER': 'test',
                'KANBAN_DB_PASSWORD': 'test',
                'KANBAN_DB_NAME': 'test',
            }):
                backend = MySQLBackend()
        self.assertIn(backend.backend_type, ('mysql', 'sqlite'))

    def test_db_cursor_context_manager(self):
        """db_cursor must work as a context manager yielding a cursor."""
        from kanban_mcp.db.mysql_backend import MySQLBackend
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool.return_value = mock_pool
        mock_pool.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        with patch('kanban_mcp.db.mysql_backend.MySQLConnectionPool',
                   return_value=mock_pool):
            with patch.dict(os.environ, {
                'KANBAN_DB_USER': 'test',
                'KANBAN_DB_PASSWORD': 'test',
                'KANBAN_DB_NAME': 'test',
            }):
                backend = MySQLBackend()

        with backend.db_cursor() as cursor:
            self.assertIsNotNone(cursor)

    def test_db_cursor_dictionary_mode(self):
        """db_cursor(dictionary=True) must pass dictionary=True to cursor."""
        from kanban_mcp.db.mysql_backend import MySQLBackend
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_pool.get_connection.return_value = mock_conn

        with patch('kanban_mcp.db.mysql_backend.MySQLConnectionPool',
                   return_value=mock_pool):
            with patch.dict(os.environ, {
                'KANBAN_DB_USER': 'test',
                'KANBAN_DB_PASSWORD': 'test',
                'KANBAN_DB_NAME': 'test',
            }):
                backend = MySQLBackend()

        with backend.db_cursor(dictionary=True) as cursor:  # noqa: F841
            pass
        mock_conn.cursor.assert_called_with(dictionary=True)

    def test_db_cursor_commit_mode(self):
        """db_cursor(commit=True) must commit on success."""
        from kanban_mcp.db.mysql_backend import MySQLBackend
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_pool.get_connection.return_value = mock_conn

        with patch('kanban_mcp.db.mysql_backend.MySQLConnectionPool',
                   return_value=mock_pool):
            with patch.dict(os.environ, {
                'KANBAN_DB_USER': 'test',
                'KANBAN_DB_PASSWORD': 'test',
                'KANBAN_DB_NAME': 'test',
            }):
                backend = MySQLBackend()

        with backend.db_cursor(commit=True) as cursor:  # noqa: F841
            pass
        mock_conn.commit.assert_called_once()

    def test_db_cursor_commit_rollback_on_error(self):
        """db_cursor(commit=True) must rollback on exception."""
        from kanban_mcp.db.mysql_backend import MySQLBackend
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_pool.get_connection.return_value = mock_conn

        with patch('kanban_mcp.db.mysql_backend.MySQLConnectionPool',
                   return_value=mock_pool):
            with patch.dict(os.environ, {
                'KANBAN_DB_USER': 'test',
                'KANBAN_DB_PASSWORD': 'test',
                'KANBAN_DB_NAME': 'test',
            }):
                backend = MySQLBackend()

        with self.assertRaises(RuntimeError):
            with backend.db_cursor(commit=True) as cursor:  # noqa: F841
                raise RuntimeError("test error")
        mock_conn.rollback.assert_called_once()

    def test_search_fulltext_returns_correct_structure(self):
        """search_fulltext must return {items, updates, total_count}."""
        from kanban_mcp.db.mysql_backend import MySQLBackend
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        with patch('kanban_mcp.db.mysql_backend.MySQLConnectionPool',
                   return_value=mock_pool):
            with patch.dict(os.environ, {
                'KANBAN_DB_USER': 'test',
                'KANBAN_DB_PASSWORD': 'test',
                'KANBAN_DB_NAME': 'test',
            }):
                backend = MySQLBackend()

        result = backend.search_fulltext('proj123', 'test query', 20)
        self.assertIn('items', result)
        self.assertIn('updates', result)
        self.assertIn('total_count', result)
        self.assertIsInstance(result['items'], list)
        self.assertIsInstance(result['updates'], list)
        self.assertIsInstance(result['total_count'], int)


# ---------------------------------------------------------------------------
# Backend factory tests
# ---------------------------------------------------------------------------

class TestBackendFactory(unittest.TestCase):
    """Tests for create_backend() factory."""

    def test_default_creates_mysql_when_creds_present(self):
        """With KANBAN_DB_* env vars, factory returns MySQLBackend."""
        from kanban_mcp.db import create_backend
        from kanban_mcp.db.mysql_backend import MySQLBackend
        with patch('kanban_mcp.db.mysql_backend.MySQLConnectionPool'):
            with patch.dict(os.environ, {
                'KANBAN_DB_USER': 'test',
                'KANBAN_DB_PASSWORD': 'test',
                'KANBAN_DB_NAME': 'test',
            }):
                backend = create_backend()
        self.assertIsInstance(backend, MySQLBackend)

    def test_explicit_backend_type_respected(self):
        """KANBAN_BACKEND=mysql forces MySQLBackend."""
        from kanban_mcp.db import create_backend
        from kanban_mcp.db.mysql_backend import MySQLBackend
        with patch('kanban_mcp.db.mysql_backend.MySQLConnectionPool'):
            with patch.dict(os.environ, {
                'KANBAN_BACKEND': 'mysql',
                'KANBAN_DB_USER': 'test',
                'KANBAN_DB_PASSWORD': 'test',
                'KANBAN_DB_NAME': 'test',
            }):
                backend = create_backend()
        self.assertIsInstance(backend, MySQLBackend)

    def test_invalid_backend_type_raises(self):
        """KANBAN_BACKEND=postgres raises ValueError."""
        from kanban_mcp.db import create_backend
        with patch.dict(os.environ, {
            'KANBAN_BACKEND': 'postgres',
            'KANBAN_DB_USER': 'test',
            'KANBAN_DB_PASSWORD': 'test',
            'KANBAN_DB_NAME': 'test',
        }):
            with self.assertRaises(ValueError) as ctx:
                create_backend()
            self.assertIn('postgres', str(ctx.exception))

    def test_missing_mysql_creds_raises(self):
        """Explicit MySQL backend without credentials raises ValueError."""
        from kanban_mcp.db import create_backend
        env = os.environ.copy()
        for key in ('KANBAN_DB_USER', 'KANBAN_DB_PASSWORD',
                    'KANBAN_DB_NAME', 'KANBAN_BACKEND'):
            env.pop(key, None)
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValueError):
                create_backend(backend_type='mysql')

    def test_auto_detect_sqlite_when_no_mysql_creds(self):
        """No KANBAN_DB_* env vars -> SQLiteBackend."""
        from kanban_mcp.db import create_backend
        from kanban_mcp.db.sqlite_backend import SQLiteBackend
        env = os.environ.copy()
        for key in ('KANBAN_DB_USER', 'KANBAN_DB_PASSWORD',
                    'KANBAN_DB_NAME', 'KANBAN_BACKEND'):
            env.pop(key, None)
        with patch.dict(os.environ, env, clear=True):
            backend = create_backend(db_path=':memory:')
        self.assertIsInstance(backend, SQLiteBackend)

    def test_auto_detect_mysql_when_creds_present(self):
        """All three KANBAN_DB_* set -> MySQLBackend."""
        from kanban_mcp.db import create_backend
        from kanban_mcp.db.mysql_backend import MySQLBackend
        with patch('kanban_mcp.db.mysql_backend.MySQLConnectionPool'):
            with patch.dict(os.environ, {
                'KANBAN_DB_USER': 'test',
                'KANBAN_DB_PASSWORD': 'test',
                'KANBAN_DB_NAME': 'test',
            }):
                # Remove KANBAN_BACKEND to test auto-detection
                env = os.environ.copy()
                env.pop('KANBAN_BACKEND', None)
                with patch.dict(os.environ, env, clear=True):
                    os.environ['KANBAN_DB_USER'] = 'test'
                    os.environ['KANBAN_DB_PASSWORD'] = 'test'
                    os.environ['KANBAN_DB_NAME'] = 'test'
                    backend = create_backend()
        self.assertIsInstance(backend, MySQLBackend)

    def test_explicit_sqlite_backend(self):
        """KANBAN_BACKEND=sqlite -> SQLiteBackend."""
        from kanban_mcp.db import create_backend
        from kanban_mcp.db.sqlite_backend import SQLiteBackend
        with patch.dict(os.environ, {
            'KANBAN_BACKEND': 'sqlite',
        }):
            backend = create_backend(db_path=':memory:')
        self.assertIsInstance(backend, SQLiteBackend)

    def test_explicit_mysql_overrides_missing_creds(self):
        """KANBAN_BACKEND=mysql without creds -> ValueError."""
        from kanban_mcp.db import create_backend
        env = os.environ.copy()
        for key in ('KANBAN_DB_USER', 'KANBAN_DB_PASSWORD',
                    'KANBAN_DB_NAME'):
            env.pop(key, None)
        env['KANBAN_BACKEND'] = 'mysql'
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValueError):
                create_backend()

    def test_factory_passes_kwargs_to_backend(self):
        """create_backend should forward kwargs to the backend constructor."""
        from kanban_mcp.db import create_backend
        with patch('kanban_mcp.db.mysql_backend.MySQLConnectionPool') \
                as mock_pool:  # noqa: F841
            backend = create_backend(
                user='myuser', password='mypass', database='mydb',
                pool_size=3)
        self.assertEqual(backend.config['user'], 'myuser')
        self.assertEqual(backend.config['database'], 'mydb')


# ---------------------------------------------------------------------------
# MySQL-specific backend tests
# ---------------------------------------------------------------------------

class TestMySQLBackend(unittest.TestCase):
    """MySQL-specific backend tests."""

    def _make_backend(self, **kwargs):
        from kanban_mcp.db.mysql_backend import MySQLBackend
        with patch('kanban_mcp.db.mysql_backend.MySQLConnectionPool'):
            with patch.dict(os.environ, {
                'KANBAN_DB_USER': 'test',
                'KANBAN_DB_PASSWORD': 'test',
                'KANBAN_DB_NAME': 'test',
            }):
                return MySQLBackend(**kwargs)

    def test_placeholder_is_percent_s(self):
        backend = self._make_backend()
        self.assertEqual(backend.placeholder, '%s')

    def test_insert_ignore_syntax(self):
        backend = self._make_backend()
        self.assertEqual(backend.insert_ignore, 'INSERT IGNORE')

    def test_backend_type_is_mysql(self):
        backend = self._make_backend()
        self.assertEqual(backend.backend_type, 'mysql')

    def test_pool_size_configurable(self):
        from kanban_mcp.db.mysql_backend import MySQLBackend
        with patch('kanban_mcp.db.mysql_backend.MySQLConnectionPool') \
                as mock_pool_cls:
            with patch.dict(os.environ, {
                'KANBAN_DB_USER': 'test',
                'KANBAN_DB_PASSWORD': 'test',
                'KANBAN_DB_NAME': 'test',
            }):
                backend = MySQLBackend(pool_size=3)  # noqa: F841
        # Verify pool_size=3 was passed to MySQLConnectionPool
        call_kwargs = mock_pool_cls.call_args
        self.assertEqual(call_kwargs[1].get('pool_size')
                         or call_kwargs.kwargs.get('pool_size'), 3)

    def test_connection_pool_created(self):
        from kanban_mcp.db.mysql_backend import MySQLBackend
        with patch('kanban_mcp.db.mysql_backend.MySQLConnectionPool') \
                as mock_pool_cls:
            with patch.dict(os.environ, {
                'KANBAN_DB_USER': 'test',
                'KANBAN_DB_PASSWORD': 'test',
                'KANBAN_DB_NAME': 'test',
            }):
                backend = MySQLBackend()
        mock_pool_cls.assert_called_once()
        self.assertIsNotNone(backend._pool)

    def test_port_passed_to_pool(self):
        from kanban_mcp.db.mysql_backend import MySQLBackend
        with patch('kanban_mcp.db.mysql_backend.MySQLConnectionPool') \
                as mock_pool_cls:
            with patch.dict(os.environ, {
                'KANBAN_DB_USER': 'test',
                'KANBAN_DB_PASSWORD': 'test',
                'KANBAN_DB_NAME': 'test',
            }):
                backend = MySQLBackend(port=3307)  # noqa: F841
        call_kwargs = mock_pool_cls.call_args
        # port should be in the kwargs passed to pool
        self.assertEqual(call_kwargs[1].get('port')
                         or call_kwargs.kwargs.get('port'), 3307)

    def test_now_func_returns_valid_sql(self):
        """now_func must return a SQL timestamp expression."""
        backend = self._make_backend()
        self.assertEqual(backend.now_func, 'NOW()')

    def test_is_duplicate_error_true(self):
        """is_duplicate_error returns True for MySQL duplicate entry."""
        backend = self._make_backend()
        exc = Exception("1062 (23000): Duplicate entry 'foo' for key")
        self.assertTrue(backend.is_duplicate_error(exc))

    def test_is_duplicate_error_false(self):
        """is_duplicate_error returns False for unrelated errors."""
        backend = self._make_backend()
        exc = Exception("Table not found")
        self.assertFalse(backend.is_duplicate_error(exc))

    def test_is_subclass_of_database_backend(self):
        """MySQLBackend must be a subclass of DatabaseBackend ABC."""
        from kanban_mcp.db.base import DatabaseBackend
        from kanban_mcp.db.mysql_backend import MySQLBackend
        self.assertTrue(issubclass(MySQLBackend, DatabaseBackend))


# ---------------------------------------------------------------------------
# _sql() helper tests
# ---------------------------------------------------------------------------

class TestSqlHelper(unittest.TestCase):
    """Tests for KanbanDB._sql() placeholder translation."""

    def _make_db_with_backend(self, placeholder='%s'):
        """Create a KanbanDB with a mock backend having given placeholder."""
        from kanban_mcp.core import KanbanDB
        mock_backend = MagicMock()
        mock_backend.placeholder = placeholder
        with patch('kanban_mcp.db.mysql_backend.MySQLConnectionPool'):
            with patch.dict(os.environ, {
                'KANBAN_DB_USER': 'test',
                'KANBAN_DB_PASSWORD': 'test',
                'KANBAN_DB_NAME': 'test',
            }):
                db = KanbanDB(backend=mock_backend)
        return db

    def test_noop_on_mysql_backend(self):
        """_sql() returns query unchanged when backend uses %s."""
        db = self._make_db_with_backend(placeholder='%s')
        query = "SELECT * FROM items WHERE id = %s AND project_id = %s"
        self.assertEqual(db._sql(query), query)

    def test_translates_percent_s_to_question_mark(self):
        """_sql() converts %s to ? when backend uses ?."""
        db = self._make_db_with_backend(placeholder='?')
        query = "SELECT * FROM items WHERE id = %s AND project_id = %s"
        expected = "SELECT * FROM items WHERE id = ? AND project_id = ?"
        self.assertEqual(db._sql(query), expected)

    def test_preserves_query_structure(self):
        """_sql() only changes placeholders, nothing else."""
        db = self._make_db_with_backend(placeholder='?')
        query = "INSERT INTO items (a, b, c) VALUES (%s, %s, %s)"
        expected = "INSERT INTO items (a, b, c) VALUES (?, ?, ?)"
        self.assertEqual(db._sql(query), expected)

    def test_multiple_placeholders(self):
        """_sql() translates all %s occurrences in a single query."""
        db = self._make_db_with_backend(placeholder='?')
        query = "%s %s %s %s %s"
        expected = "? ? ? ? ?"
        self.assertEqual(db._sql(query), expected)

    def test_empty_query(self):
        """_sql() handles empty string."""
        db = self._make_db_with_backend(placeholder='?')
        self.assertEqual(db._sql(""), "")

    def test_no_placeholders(self):
        """_sql() returns query unchanged when no placeholders present."""
        db = self._make_db_with_backend(placeholder='?')
        query = "SELECT COUNT(*) FROM items"
        self.assertEqual(db._sql(query), query)


# ---------------------------------------------------------------------------
# KanbanDB integration with backend
# ---------------------------------------------------------------------------

class TestKanbanDBWithBackend(unittest.TestCase):
    """Verify KanbanDB delegates to backend correctly."""

    def test_init_creates_backend(self):
        """KanbanDB() should create a backend via factory."""
        from kanban_mcp.core import KanbanDB
        with patch('kanban_mcp.db.mysql_backend.MySQLConnectionPool'):
            with patch.dict(os.environ, {
                'KANBAN_DB_USER': 'test',
                'KANBAN_DB_PASSWORD': 'test',
                'KANBAN_DB_NAME': 'test',
            }):
                db = KanbanDB()
        self.assertTrue(hasattr(db, '_backend'))
        self.assertIsNotNone(db._backend)

    def test_init_accepts_explicit_backend(self):
        """KanbanDB(backend=my_backend) should use the provided backend."""
        from kanban_mcp.core import KanbanDB
        mock_backend = MagicMock()
        mock_backend.placeholder = '%s'
        mock_backend.config = {
            'host': 'localhost', 'port': 3306,
            'user': 'test', 'password': 'test',
            'database': 'test',
        }
        db = KanbanDB(backend=mock_backend)
        self.assertIs(db._backend, mock_backend)

    def test_db_cursor_delegates_to_backend(self):
        """KanbanDB._db_cursor should call backend.db_cursor."""
        from kanban_mcp.core import KanbanDB
        mock_backend = MagicMock()
        mock_backend.placeholder = '%s'
        mock_backend.config = {
            'host': 'localhost', 'port': 3306,
            'user': 'test', 'password': 'test',
            'database': 'test',
        }
        mock_cursor = MagicMock()
        mock_backend.db_cursor.return_value.__enter__ = \
            MagicMock(return_value=mock_cursor)
        mock_backend.db_cursor.return_value.__exit__ = \
            MagicMock(return_value=False)

        db = KanbanDB(backend=mock_backend)
        with db._db_cursor(
            dictionary=True, commit=True,
        ) as cursor:  # noqa: F841
            pass
        mock_backend.db_cursor.assert_called_with(
            dictionary=True, commit=True)

    def test_search_delegates_to_backend(self):
        """KanbanDB.search should call backend.search_fulltext."""
        from kanban_mcp.core import KanbanDB
        mock_backend = MagicMock()
        mock_backend.placeholder = '%s'
        mock_backend.config = {
            'host': 'localhost', 'port': 3306,
            'user': 'test', 'password': 'test',
            'database': 'test',
        }
        mock_backend.search_fulltext.return_value = {
            'items': [], 'updates': [], 'total_count': 0
        }
        db = KanbanDB(backend=mock_backend)
        result = db.search('proj123', 'test query', limit=10)  # noqa: F841
        mock_backend.search_fulltext.assert_called_once_with(
            'proj123', 'test query', 10)

    def test_config_still_accessible(self):
        """KanbanDB.config must still return the config dict."""
        from kanban_mcp.core import KanbanDB
        mock_backend = MagicMock()
        mock_backend.placeholder = '%s'
        mock_backend.config = {
            'host': 'myhost', 'port': 3306,
            'user': 'myuser', 'password': 'mypass',
            'database': 'mydb',
        }
        db = KanbanDB(backend=mock_backend)
        self.assertEqual(db.config['host'], 'myhost')
        self.assertEqual(db.config['user'], 'myuser')
        self.assertEqual(db.config['database'], 'mydb')

    def test_backend_type_accessible(self):
        """KanbanDB._backend.backend_type should be accessible."""
        from kanban_mcp.core import KanbanDB
        with patch('kanban_mcp.db.mysql_backend.MySQLConnectionPool'):
            with patch.dict(os.environ, {
                'KANBAN_DB_USER': 'test',
                'KANBAN_DB_PASSWORD': 'test',
                'KANBAN_DB_NAME': 'test',
            }):
                db = KanbanDB()
        self.assertEqual(db._backend.backend_type, 'mysql')


if __name__ == "__main__":
    unittest.main()
