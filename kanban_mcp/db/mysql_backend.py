"""MySQL/MariaDB database backend."""

import logging
import os
from contextlib import contextmanager
from typing import Any, Dict

from mysql.connector.pooling import MySQLConnectionPool

from kanban_mcp.db.base import DatabaseBackend

logger = logging.getLogger(__name__)

# Shared pool counter across all MySQLBackend instances
_pool_counter = 0


class MySQLBackend(DatabaseBackend):
    """MySQL/MariaDB backend using connection pooling."""

    def __init__(self, host: str = None, user: str = None,
                 password: str = None, database: str = None,
                 pool_size: int = None, port: int = None):
        resolved_user = user or os.environ.get("KANBAN_DB_USER", "")
        resolved_password = password or os.environ.get(
            "KANBAN_DB_PASSWORD", "")
        resolved_database = database or os.environ.get("KANBAN_DB_NAME", "")

        missing = []
        if not resolved_user:
            missing.append("KANBAN_DB_USER")
        if not resolved_password:
            missing.append("KANBAN_DB_PASSWORD")
        if not resolved_database:
            missing.append("KANBAN_DB_NAME")
        if missing:
            raise ValueError(
                "Missing required database credentials:"
                f" {', '.join(missing)}. "
                "Set them as environment variables or "
                "pass to constructor."
            )

        resolved_port = port or int(
            os.environ.get("KANBAN_DB_PORT", "3306"))

        self.config = {
            "host": host or os.environ.get("KANBAN_DB_HOST", "localhost"),
            "port": resolved_port,
            "user": resolved_user,
            "password": resolved_password,
            "database": resolved_database,
        }
        if pool_size is None:
            pool_size = int(os.environ.get("KANBAN_DB_POOL_SIZE", "5"))

        global _pool_counter
        _pool_counter += 1
        self._pool = MySQLConnectionPool(
            pool_name=f"kanban_pool_{_pool_counter}",
            pool_size=pool_size,
            **self.config
        )

    def _get_connection(self):
        """Get a database connection from the pool."""
        return self._pool.get_connection()

    @contextmanager
    def db_cursor(self, dictionary=False, commit=False):
        """Context manager for database cursor with automatic cleanup."""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=dictionary)
        try:
            yield cursor
            if commit:
                conn.commit()
        except Exception:
            if commit:
                conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    def search_fulltext(self, project_id: str, query: str,
                        limit: int) -> Dict[str, Any]:
        """MySQL fulltext search using MATCH...AGAINST."""
        items = []
        updates = []

        # Use BOOLEAN MODE if query contains wildcard, otherwise NATURAL
        use_boolean = '*' in query
        mode = ('IN BOOLEAN MODE' if use_boolean
                else 'IN NATURAL LANGUAGE MODE')

        with self.db_cursor(dictionary=True) as cursor:
            # Search items (title and description)
            cursor.execute(f"""
                SELECT i.id, i.title, i.description,
                       it.name as type_name, s.name as status_name,
                       MATCH(i.title, i.description)
                       AGAINST(%s {mode}) as score
                FROM items i
                JOIN item_types it ON i.type_id = it.id
                JOIN statuses s ON i.status_id = s.id
                WHERE i.project_id = %s
                  AND MATCH(i.title, i.description) AGAINST(%s {mode})
                ORDER BY score DESC
                LIMIT %s
            """, (query, project_id, query, limit))  # nosec B608

            for row in cursor.fetchall():
                snippet = row['title']
                if row['description']:
                    snippet = row['description'][:100] + \
                        ('...' if len(row['description']) > 100 else '')

                items.append({
                    'id': row['id'],
                    'title': row['title'],
                    'snippet': snippet,
                    'score': float(row['score']),
                    'type_name': row['type_name'],
                    'status_name': row['status_name']
                })

            # Search updates (content)
            cursor.execute(f"""
                SELECT u.id, u.content, u.created_at,
                       MATCH(u.content) AGAINST(%s {mode}) as score
                FROM updates u
                WHERE u.project_id = %s
                  AND MATCH(u.content) AGAINST(%s {mode})
                ORDER BY score DESC
                LIMIT %s
            """, (query, project_id, query, limit))  # nosec B608

            for row in cursor.fetchall():
                snippet = row['content'][:100] + \
                    ('...' if len(row['content']) > 100 else '')
                updates.append({
                    'id': row['id'],
                    'snippet': snippet,
                    'score': float(row['score']),
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
        auto_migrate(self.config)

    @property
    def placeholder(self) -> str:
        return '%s'

    @property
    def insert_ignore(self) -> str:
        return 'INSERT IGNORE'

    @property
    def backend_type(self) -> str:
        return 'mysql'
