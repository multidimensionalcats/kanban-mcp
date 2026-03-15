"""Pluggable database backend for kanban-mcp."""

import os

from kanban_mcp.db.base import DatabaseBackend
from kanban_mcp.db.sqlite_backend import SQLiteBackend

__all__ = [
    'DatabaseBackend', 'SQLiteBackend', 'create_backend',
]

# Lazy-import MySQLBackend to avoid hard dependency
try:
    from kanban_mcp.db.mysql_backend import MySQLBackend
    __all__.append('MySQLBackend')
    _HAS_MYSQL = True
except ImportError:
    _HAS_MYSQL = False

_VALID_BACKENDS = {'mysql', 'sqlite'}

# MySQL-specific kwargs that should not be passed to SQLiteBackend
_MYSQL_KWARGS = {
    'host', 'user', 'password', 'database', 'pool_size', 'port',
}


def _detect_backend_type() -> str:
    """Auto-detect backend: MySQL if creds present, else SQLite."""
    explicit = os.environ.get('KANBAN_BACKEND')
    if explicit:
        return explicit
    if (os.environ.get('KANBAN_DB_USER')
            and os.environ.get('KANBAN_DB_PASSWORD')
            and os.environ.get('KANBAN_DB_NAME')):
        return 'mysql'
    return 'sqlite'


def create_backend(backend_type: str = None, **kwargs) -> DatabaseBackend:
    """Create a database backend instance.

    Args:
        backend_type: 'mysql' or 'sqlite'. If None, auto-detected:
            MySQL if KANBAN_DB_USER/PASSWORD/NAME all set, else SQLite.
            KANBAN_BACKEND env var always wins if set.
        **kwargs: Passed to the backend constructor.

    Returns:
        A DatabaseBackend instance.

    Raises:
        ValueError: If backend_type is not in the whitelist or
            MySQL is requested but mysql-connector-python is not
            installed.
    """
    if backend_type is None:
        backend_type = _detect_backend_type()

    if backend_type not in _VALID_BACKENDS:
        raise ValueError(
            f"Unknown backend type: '{backend_type}'. "
            f"Must be one of: {', '.join(sorted(_VALID_BACKENDS))}"
        )

    if backend_type == 'mysql':
        if not _HAS_MYSQL:
            raise ValueError(
                "MySQL backend requested but"
                " mysql-connector-python is not installed."
                " Install with: pip install kanban-mcp[mysql]"
            )
        return MySQLBackend(**kwargs)

    if backend_type == 'sqlite':
        # Filter out MySQL-specific kwargs
        sqlite_kwargs = {
            k: v for k, v in kwargs.items()
            if k not in _MYSQL_KWARGS
        }
        return SQLiteBackend(**sqlite_kwargs)

    raise ValueError(
        f"Backend '{backend_type}' is not yet implemented."
    )
