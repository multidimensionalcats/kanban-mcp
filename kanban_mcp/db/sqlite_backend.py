"""SQLite database backend."""

import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from kanban_mcp.db.base import DatabaseBackend

# Register custom timestamp adapter/converter to replace the
# deprecated built-in ones (removed in a future Python version).
sqlite3.register_adapter(
    datetime, lambda dt: dt.isoformat())
sqlite3.register_converter(
    "TIMESTAMP", lambda b: datetime.fromisoformat(b.decode()))

logger = logging.getLogger(__name__)


def _get_default_db_path() -> str:
    """Return the default SQLite database path.

    Respects XDG_DATA_HOME, defaults to ~/.local/share/kanban-mcp/kanban.db
    """
    data_home = os.environ.get(
        'XDG_DATA_HOME',
        str(Path.home() / '.local' / 'share'))
    return str(Path(data_home) / 'kanban-mcp' / 'kanban.db')


class SQLiteBackend(DatabaseBackend):
    """SQLite backend with WAL mode for concurrent access."""

    def __init__(self, db_path: str = None):
        # Resolve path: constructor arg > env var > XDG default
        if db_path is not None:
            self._db_path = db_path
        else:
            self._db_path = os.environ.get(
                'KANBAN_SQLITE_PATH',
                _get_default_db_path())

        # Auto-create parent directory for file-based databases
        if self._db_path != ':memory:':
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

        # Open persistent connection
        self._conn = sqlite3.connect(
            self._db_path,
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES)

        # Enable WAL mode for file-based databases
        if self._db_path != ':memory:':
            self._conn.execute('PRAGMA journal_mode=WAL')

        # Enable foreign keys and set busy timeout
        self._conn.execute('PRAGMA foreign_keys=ON')
        self._conn.execute('PRAGMA busy_timeout=5000')

    @contextmanager
    def db_cursor(self, dictionary=False, commit=False):
        """Context manager for database cursor.

        When dictionary=True, rows are returned as real dict objects.
        Thread-safe: does not mutate shared connection state.
        """
        cursor = self._conn.cursor()
        try:
            if dictionary:
                yield _DictCursorWrapper(cursor)
            else:
                yield cursor
            if commit:
                self._conn.commit()
        except Exception:
            if commit:
                self._conn.rollback()
            raise
        finally:
            cursor.close()

    def search_fulltext(self, project_id: str, query: str,
                        limit: int) -> Dict[str, Any]:
        """LIKE-based search on items and updates."""
        items = []
        updates = []
        # Escape SQL LIKE wildcards in user input
        escaped = (query.replace('\\', '\\\\')
                   .replace('%', '\\%')
                   .replace('_', '\\_'))
        like_pattern = f'%{escaped}%'

        with self.db_cursor(dictionary=True) as cursor:
            # Search items — title matches score higher
            cursor.execute("""
                SELECT i.id, i.title, i.description,
                       it.name as type_name, s.name as status_name,
                       CASE
                           WHEN i.title LIKE ? ESCAPE '\\' THEN 2.0
                           ELSE 1.0
                       END as score
                FROM items i
                JOIN item_types it ON i.type_id = it.id
                JOIN statuses s ON i.status_id = s.id
                WHERE i.project_id = ?
                  AND (i.title LIKE ? ESCAPE '\\'
                       OR i.description LIKE ? ESCAPE '\\')
                ORDER BY score DESC
                LIMIT ?
            """, (like_pattern, project_id,
                  like_pattern, like_pattern, limit))

            for row in cursor.fetchall():
                snippet = row['title']
                if row['description']:
                    desc = row['description']
                    snippet = desc[:100] + ('...' if len(desc) > 100 else '')

                items.append({
                    'id': row['id'],
                    'title': row['title'],
                    'snippet': snippet,
                    'score': float(row['score']),
                    'type_name': row['type_name'],
                    'status_name': row['status_name']
                })

            # Search updates
            cursor.execute("""
                SELECT u.id, u.content, u.created_at
                FROM updates u
                WHERE u.project_id = ?
                  AND u.content LIKE ? ESCAPE '\\'
                ORDER BY u.created_at DESC
                LIMIT ?
            """, (project_id, like_pattern, limit))

            for row in cursor.fetchall():
                content = row['content']
                snippet = content[:100] + (
                    '...' if len(content) > 100 else '')
                updates.append({
                    'id': row['id'],
                    'snippet': snippet,
                    'score': 1.0,
                    'created_at': row['created_at']
                })

        return {
            'items': items,
            'updates': updates,
            'total_count': len(items) + len(updates)
        }

    def run_migrations(self, migrations_dir: str) -> None:
        """Apply pending migrations — delegates to setup module."""
        from kanban_mcp.setup import auto_migrate
        auto_migrate(self)

    @property
    def placeholder(self) -> str:
        return '?'

    @property
    def insert_ignore(self) -> str:
        return 'INSERT OR IGNORE'

    @property
    def backend_type(self) -> str:
        return 'sqlite'

    @property
    def now_func(self) -> str:
        return "datetime('now')"

    def is_duplicate_error(self, exc: Exception) -> bool:
        return 'UNIQUE constraint failed' in str(exc)

    @property
    def config(self) -> dict:
        return {'database': self._db_path}


class _DictCursorWrapper:
    """Wraps a sqlite3 Cursor to return real dicts from fetch methods.

    Converts tuples to dicts using cursor.description column names.
    Does not rely on connection.row_factory, so it is thread-safe.
    """

    def __init__(self, cursor):
        self._cursor = cursor

    def _to_dict(self, row):
        if row is None:
            return None
        cols = [d[0] for d in self._cursor.description]
        return dict(zip(cols, row))

    def execute(self, *args, **kwargs):
        return self._cursor.execute(*args, **kwargs)

    def executemany(self, *args, **kwargs):
        return self._cursor.executemany(*args, **kwargs)

    def fetchone(self):
        return self._to_dict(self._cursor.fetchone())

    def fetchall(self):
        cols = [d[0] for d in self._cursor.description]
        return [dict(zip(cols, row)) for row in self._cursor.fetchall()]

    def fetchmany(self, size=None):
        if size is None:
            rows = self._cursor.fetchmany()
        else:
            rows = self._cursor.fetchmany(size)
        cols = [d[0] for d in self._cursor.description]
        return [dict(zip(cols, row)) for row in rows]

    def close(self):
        self._cursor.close()

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def description(self):
        return self._cursor.description
