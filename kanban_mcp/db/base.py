"""Abstract base class for database backends."""

from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Any, Dict


class DatabaseBackend(ABC):
    """Interface that all database backends must implement."""

    @abstractmethod
    @contextmanager
    def db_cursor(self, dictionary=False, commit=False):
        """Yield a cursor. Same contract as KanbanDB._db_cursor.

        Args:
            dictionary: If True, return rows as dicts.
            commit: If True, commit on success, rollback on error.

        Yields:
            cursor: Database cursor object
        """

    @abstractmethod
    def search_fulltext(self, project_id: str, query: str,
                        limit: int) -> Dict[str, Any]:
        """Backend-specific fulltext search.

        Returns:
            Dict with 'items', 'updates', and 'total_count' keys.
        """

    @abstractmethod
    def run_migrations(self, migrations_dir: str) -> None:
        """Apply pending migrations from the given directory."""

    @property
    @abstractmethod
    def placeholder(self) -> str:
        """Parameter placeholder: '%s' for MySQL, '?' for SQLite."""

    @property
    @abstractmethod
    def insert_ignore(self) -> str:
        """INSERT IGNORE syntax: 'INSERT IGNORE' or 'INSERT OR IGNORE'."""

    @property
    @abstractmethod
    def backend_type(self) -> str:
        """Backend identifier: 'mysql' or 'sqlite'."""
