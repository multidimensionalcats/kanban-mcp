"""Pluggable database backend for kanban-mcp."""

import os

from kanban_mcp.db.base import DatabaseBackend
from kanban_mcp.db.mysql_backend import MySQLBackend

__all__ = ['DatabaseBackend', 'MySQLBackend', 'create_backend']

_VALID_BACKENDS = {'mysql', 'sqlite'}


def create_backend(backend_type: str = None, **kwargs) -> DatabaseBackend:
    """Create a database backend instance.

    Args:
        backend_type: 'mysql' or 'sqlite'. If None, reads from
            KANBAN_BACKEND env var, defaulting to 'mysql'.
        **kwargs: Passed to the backend constructor.

    Returns:
        A DatabaseBackend instance.

    Raises:
        ValueError: If backend_type is not in the whitelist.
    """
    if backend_type is None:
        backend_type = os.environ.get('KANBAN_BACKEND', 'mysql')

    if backend_type not in _VALID_BACKENDS:
        raise ValueError(
            f"Unknown backend type: '{backend_type}'. "
            f"Must be one of: {', '.join(sorted(_VALID_BACKENDS))}"
        )

    if backend_type == 'mysql':
        return MySQLBackend(**kwargs)

    # sqlite not yet implemented
    raise ValueError(
        f"Backend '{backend_type}' is not yet implemented."
    )
