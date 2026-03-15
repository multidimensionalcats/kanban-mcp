"""Test configuration and shared fixtures.

Sets DB credentials for test environment and provides
parametrized backend fixtures for cross-backend testing.
"""
import os

import pytest

# Set test database credentials if not already set.
# These are the development defaults; CI/Docker should set real values.
_test_defaults = {
    "KANBAN_DB_HOST": "localhost",
    "KANBAN_DB_USER": "claude",
    "KANBAN_DB_PASSWORD": "claude_code_password",
    "KANBAN_DB_NAME": "claude_code_kanban",
    "KANBAN_DB_POOL_SIZE": "2",
}

for key, value in _test_defaults.items():
    if not os.environ.get(key):
        os.environ[key] = value


# ---------------------------------------------------------------------------
# SQLite fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sqlite_backend(tmp_path):
    """SQLiteBackend with temp file db, migrations applied."""
    from kanban_mcp.db.sqlite_backend import SQLiteBackend
    from kanban_mcp.setup import auto_migrate

    backend = SQLiteBackend(db_path=str(tmp_path / "test.db"))
    auto_migrate(backend)
    return backend


@pytest.fixture
def sqlite_memory_backend():
    """SQLiteBackend with :memory:, migrations applied."""
    from kanban_mcp.db.sqlite_backend import SQLiteBackend
    from kanban_mcp.setup import auto_migrate

    backend = SQLiteBackend(db_path=":memory:")
    auto_migrate(backend)
    return backend


# ---------------------------------------------------------------------------
# Parametrized backend fixture
# ---------------------------------------------------------------------------

def _mysql_available():
    """Check if MySQL is available for testing."""
    try:
        from kanban_mcp.db.mysql_backend import MySQLBackend
        backend = MySQLBackend()
        with backend.db_cursor() as cursor:
            cursor.execute("SELECT 1")
        return True
    except Exception:
        return False


_MYSQL_AVAILABLE = None


def _check_mysql():
    """Cached check for MySQL availability."""
    global _MYSQL_AVAILABLE
    if _MYSQL_AVAILABLE is None:
        _MYSQL_AVAILABLE = _mysql_available()
    return _MYSQL_AVAILABLE


def _get_backend_params():
    """Return list of backend params. SQLite always, MySQL if available."""
    params = ["sqlite"]
    # MySQL parametrization is conditional
    if _check_mysql():
        params.append("mysql")
    return params


@pytest.fixture(params=_get_backend_params())
def backend(request, tmp_path):
    """Parametrized backend fixture — tests run against all backends."""
    from kanban_mcp.setup import auto_migrate

    if request.param == "sqlite":
        from kanban_mcp.db.sqlite_backend import SQLiteBackend
        b = SQLiteBackend(db_path=str(tmp_path / "test.db"))
        auto_migrate(b)
        return b
    elif request.param == "mysql":
        from kanban_mcp.db.mysql_backend import MySQLBackend
        b = MySQLBackend()
        auto_migrate(b)
        # Clean test data before each test
        with b.db_cursor(commit=True) as cursor:
            cursor.execute(
                "DELETE FROM update_items")
            cursor.execute("DELETE FROM updates")
            cursor.execute(
                "DELETE FROM item_relationships")
            cursor.execute("DELETE FROM item_tags")
            cursor.execute("DELETE FROM item_files")
            cursor.execute("DELETE FROM item_decisions")
            cursor.execute("DELETE FROM status_history")
            cursor.execute("DELETE FROM embeddings")
            cursor.execute("DELETE FROM tags")
            cursor.execute("DELETE FROM items")
            cursor.execute("DELETE FROM projects")
        return b


@pytest.fixture
def db(backend):
    """KanbanDB wired to the parametrized backend."""
    from kanban_mcp.core import KanbanDB
    return KanbanDB(backend=backend)


@pytest.fixture
def project_id(db):
    """Create a test project and return its ID."""
    return db.ensure_project("/tmp/test-project", "Test Project")
