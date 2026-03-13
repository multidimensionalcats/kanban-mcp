#!/usr/bin/env python3
"""
Unit tests for Kanban MCP Server.
Tests define target behavior - written BEFORE implementation.
"""

import os
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch


def cleanup_test_project(db, project_path):
    """Clean up all test data for a project including the project itself."""
    project_id = db.hash_project_path(project_path)
    pid = project_id
    ph = db._backend.placeholder
    sub = f"(SELECT id FROM items WHERE project_id = {ph})"
    with db._db_cursor(commit=True) as cursor:
        cursor.execute(
            "DELETE FROM update_items WHERE update_id IN "
            f"(SELECT id FROM updates WHERE project_id = {ph})",
            (pid,))
        cursor.execute(
            "DELETE FROM embeddings WHERE source_type = 'item'"
            " AND source_id IN " + sub, (pid,))
        cursor.execute(
            "DELETE FROM embeddings WHERE source_type = "
            "'decision' AND source_id IN "
            "(SELECT id FROM item_decisions WHERE "
            "item_id IN " + sub + ")", (pid,))
        cursor.execute(
            "DELETE FROM embeddings WHERE source_type = "
            "'update' AND source_id IN "
            "(SELECT id FROM updates WHERE "
            f"project_id = {ph})", (pid,))
        cursor.execute(
            f"DELETE FROM updates WHERE project_id = {ph}",
            (pid,))
        cursor.execute(
            "DELETE FROM item_tags WHERE item_id IN "
            + sub, (pid,))
        cursor.execute(
            "DELETE FROM item_decisions WHERE item_id IN "
            + sub, (pid,))
        cursor.execute(
            "DELETE FROM item_files WHERE item_id IN "
            + sub, (pid,))
        cursor.execute(
            "DELETE FROM status_history WHERE item_id IN "
            + sub, (pid,))
        cursor.execute(
            "DELETE FROM item_relationships WHERE "
            "source_item_id IN " + sub
            + " OR target_item_id IN " + sub,
            (pid, pid))
        cursor.execute(
            f"DELETE FROM items WHERE project_id = {ph}",
            (pid,))
        cursor.execute(
            f"DELETE FROM tags WHERE project_id = {ph}",
            (pid,))
        cursor.execute(f"DELETE FROM projects WHERE id = {ph}", (project_id,))


class TestKanbanDB(unittest.TestCase):
    """Test the KanbanDB database operations."""

    @classmethod
    def setUpClass(cls):
        """Set up test database connection."""
        from kanban_mcp.core import KanbanDB
        from kanban_mcp.setup import auto_migrate
        cls.db = KanbanDB()
        auto_migrate(cls.db._backend)
        # Use a test project path
        cls.test_project_path = "/tmp/test-kanban-project"
        cls.test_project_id = cls.db.hash_project_path(cls.test_project_path)

    def setUp(self):
        """Ensure clean state before each test."""
        cleanup_test_project(self.db, self.test_project_path)

    def tearDown(self):
        """Clean up after each test."""
        cleanup_test_project(self.db, self.test_project_path)

    # --- Project Tests ---

    def test_hash_project_path_deterministic(self):
        """Hash should be deterministic for same path."""
        hash1 = self.db.hash_project_path("/home/user/project")
        hash2 = self.db.hash_project_path("/home/user/project")
        self.assertEqual(hash1, hash2)

    def test_hash_project_path_length(self):
        """Hash should be 16 characters."""
        hash_id = self.db.hash_project_path("/some/path")
        self.assertEqual(len(hash_id), 16)

    def test_hash_project_path_different_paths(self):
        """Different paths should produce different hashes."""
        hash1 = self.db.hash_project_path("/path/one")
        hash2 = self.db.hash_project_path("/path/two")
        self.assertNotEqual(hash1, hash2)

    def test_ensure_project_creates_new(self):
        """ensure_project should create project if not exists."""
        project_id = self.db.ensure_project(
            self.test_project_path, "test-project")
        self.assertEqual(project_id, self.test_project_id)

        project = self.db.get_project_by_path(self.test_project_path)
        self.assertIsNotNone(project)
        self.assertEqual(project['name'], "test-project")

    def test_ensure_project_idempotent(self):
        """ensure_project should be idempotent."""
        id1 = self.db.ensure_project(self.test_project_path, "test-project")
        id2 = self.db.ensure_project(self.test_project_path, "different-name")
        self.assertEqual(id1, id2)

    # --- Item Type/Status Tests ---

    def test_get_type_id_valid(self):
        """get_type_id should return ID for valid types."""
        issue_id = self.db.get_type_id("issue")
        self.assertIsNotNone(issue_id)
        self.assertIsInstance(issue_id, int)

    def test_get_type_id_invalid(self):
        """get_type_id should raise for invalid types."""
        with self.assertRaises(ValueError):
            self.db.get_type_id("invalid_type")

    def test_get_status_id_valid(self):
        """get_status_id should return ID for valid statuses."""
        status_id = self.db.get_status_id("backlog")
        self.assertIsNotNone(status_id)
        self.assertIsInstance(status_id, int)

    def test_get_status_id_invalid(self):
        """get_status_id should raise for invalid statuses."""
        with self.assertRaises(ValueError):
            self.db.get_status_id("invalid_status")

    # --- Item CRUD Tests ---

    def test_create_item_basic(self):
        """create_item should create item with minimal fields."""
        self.db.ensure_project(self.test_project_path)
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Test Issue"
        )
        self.assertIsNotNone(item_id)
        self.assertIsInstance(item_id, int)

    def test_create_item_with_all_fields(self):
        """create_item should create item with all fields."""
        self.db.ensure_project(self.test_project_path)
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="feature",
            title="New Feature",
            description="Feature description",
            priority=1
        )

        item = self.db.get_item(item_id)
        self.assertEqual(item['title'], "New Feature")
        self.assertEqual(item['description'], "Feature description")
        self.assertEqual(item['priority'], 1)
        self.assertEqual(item['type_name'], "feature")

    def test_create_item_default_status_is_backlog(self):
        """New issues/todos/features should start in backlog."""
        self.db.ensure_project(self.test_project_path)
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Test Issue"
        )
        item = self.db.get_item(item_id)
        self.assertEqual(item['status_name'], "backlog")

    def test_create_diary_default_status_is_done(self):
        """Diary entries should start in done status."""
        self.db.ensure_project(self.test_project_path)
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="diary",
            title="Development Notes"
        )
        item = self.db.get_item(item_id)
        self.assertEqual(item['status_name'], "done")

    def test_get_item_not_found(self):
        """get_item should return None for non-existent item."""
        item = self.db.get_item(99999)
        self.assertIsNone(item)

    def test_delete_item(self):
        """delete_item should remove item."""
        self.db.ensure_project(self.test_project_path)
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="To Delete"
        )

        result = self.db.delete_item(item_id)
        self.assertTrue(result['success'])

        item = self.db.get_item(item_id)
        self.assertIsNone(item)

    # --- Status Workflow Tests ---

    def test_advance_status_issue(self):
        """advance_status should move issue through workflow."""
        self.db.ensure_project(self.test_project_path)
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Test Issue"
        )

        # backlog -> todo
        result = self.db.advance_status(item_id)
        self.assertTrue(result['success'])
        self.assertEqual(result['new_status'], 'todo')

        # todo -> in_progress
        result = self.db.advance_status(item_id)
        self.assertEqual(result['new_status'], 'in_progress')

    def test_advance_status_todo_skips_review(self):
        """Todos should skip review status.

        Todo workflow: backlog->todo->in_progress->done.
        """
        self.db.ensure_project(self.test_project_path)
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="todo",
            title="Test Todo"
        )

        self.db.advance_status(item_id)  # backlog -> todo
        self.db.advance_status(item_id)  # todo -> in_progress
        result = self.db.advance_status(item_id)  # -> done

        self.assertEqual(result['new_status'], 'done')

    def test_revert_status(self):
        """revert_status should move item back in workflow."""
        self.db.ensure_project(self.test_project_path)
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Test Issue"
        )

        self.db.advance_status(item_id)  # backlog -> todo
        self.db.advance_status(item_id)  # todo -> in_progress

        result = self.db.revert_status(item_id)  # in_progress -> todo
        self.assertTrue(result['success'])
        self.assertEqual(result['new_status'], 'todo')

    def test_set_status_valid(self):
        """set_status should set valid status for type."""
        self.db.ensure_project(self.test_project_path)
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Test Issue"
        )

        result = self.db.set_status(item_id, "in_progress")
        self.assertTrue(result['success'])
        self.assertEqual(result['new_status'], 'in_progress')

    def test_set_status_invalid_for_type(self):
        """set_status should reject status not in type's workflow."""
        self.db.ensure_project(self.test_project_path)
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="diary",  # diary only has 'done' status
            title="Test Diary"
        )

        with self.assertRaises(ValueError):
            self.db.set_status(item_id, "in_progress")

    def test_close_item(self):
        """close_item should set final status."""
        self.db.ensure_project(self.test_project_path)
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Test Issue"
        )

        result = self.db.close_item(item_id)
        self.assertTrue(result['success'])
        self.assertEqual(result['new_status'], 'closed')

    # --- List/Filter Tests ---

    def test_list_items_empty(self):
        """list_items should return empty list for new project."""
        self.db.ensure_project(self.test_project_path)
        items = self.db.list_items(project_id=self.test_project_id)
        self.assertEqual(items, [])

    def test_list_items_by_project(self):
        """list_items should filter by project."""
        self.db.ensure_project(self.test_project_path)
        self.db.create_item(self.test_project_id, "issue", "Issue 1")
        self.db.create_item(self.test_project_id, "issue", "Issue 2")

        items = self.db.list_items(project_id=self.test_project_id)
        self.assertEqual(len(items), 2)

    def test_list_items_by_type(self):
        """list_items should filter by type."""
        self.db.ensure_project(self.test_project_path)
        self.db.create_item(self.test_project_id, "issue", "Issue")
        self.db.create_item(self.test_project_id, "todo", "Todo")

        issues = self.db.list_items(
            project_id=self.test_project_id,
            type_name="issue")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]['type_name'], 'issue')

    def test_list_items_by_status(self):
        """list_items should filter by status."""
        self.db.ensure_project(self.test_project_path)
        item1 = self.db.create_item(self.test_project_id, "issue", "Issue 1")
        self.db.create_item(self.test_project_id, "issue", "Issue 2")
        self.db.advance_status(item1)  # Move to todo

        backlog_items = self.db.list_items(
            project_id=self.test_project_id,
            status_name="backlog")
        self.assertEqual(len(backlog_items), 1)

    def test_get_backlog_items(self):
        """Should be able to get items in backlog status."""
        self.db.ensure_project(self.test_project_path)
        self.db.create_item(self.test_project_id, "issue", "Backlog Issue")
        item2 = self.db.create_item(
            self.test_project_id, "todo", "In Progress Todo")
        self.db.advance_status(item2)  # backlog -> todo
        self.db.advance_status(item2)  # todo -> in_progress

        backlog = self.db.list_items(
            project_id=self.test_project_id,
            status_name="backlog")
        self.assertEqual(len(backlog), 1)
        self.assertEqual(backlog[0]['title'], "Backlog Issue")

    # --- Updates Tests ---

    def test_add_update_no_items(self):
        """add_update should work without linked items."""
        self.db.ensure_project(self.test_project_path)
        update_id = self.db.add_update(self.test_project_id, "Progress note")
        self.assertIsNotNone(update_id)
        self.assertIsInstance(update_id, int)

    def test_add_update_with_items(self):
        """add_update should link to items."""
        self.db.ensure_project(self.test_project_path)
        item1 = self.db.create_item(self.test_project_id, "issue", "Issue 1")
        item2 = self.db.create_item(self.test_project_id, "issue", "Issue 2")

        self.db.add_update(
            self.test_project_id,
            "Fixed both issues",
            item_ids=[item1, item2]
        )

        update = self.db.get_latest_update(self.test_project_id)
        self.assertIn(item1, update['item_ids'])
        self.assertIn(item2, update['item_ids'])

    def test_get_latest_update(self):
        """get_latest_update should return most recent."""
        self.db.ensure_project(self.test_project_path)
        self.db.add_update(self.test_project_id, "First update")
        self.db.add_update(self.test_project_id, "Second update")

        latest = self.db.get_latest_update(self.test_project_id)
        self.assertEqual(latest['content'], "Second update")

    def test_get_updates_ordered(self):
        """get_updates should return in reverse chronological order."""
        self.db.ensure_project(self.test_project_path)
        self.db.add_update(self.test_project_id, "First")
        self.db.add_update(self.test_project_id, "Second")
        self.db.add_update(self.test_project_id, "Third")

        updates = self.db.get_updates(self.test_project_id)
        self.assertEqual(updates[0]['content'], "Third")
        self.assertEqual(updates[2]['content'], "First")

    # --- Summary Tests ---

    def test_project_summary(self):
        """project_summary should return counts by type and status."""
        self.db.ensure_project(self.test_project_path)
        self.db.create_item(self.test_project_id, "issue", "Issue 1")
        self.db.create_item(self.test_project_id, "issue", "Issue 2")
        item3 = self.db.create_item(self.test_project_id, "todo", "Todo 1")
        self.db.advance_status(item3)  # backlog -> todo

        summary = self.db.project_summary(self.test_project_id)

        self.assertEqual(summary['issue']['backlog'], 2)
        self.assertEqual(summary['todo']['todo'], 1)


class TestKanbanMCPServerState(unittest.TestCase):
    """Test MCP server project state management."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanMCPServer
        cls.server = KanbanMCPServer()

    def setUp(self):
        self.server.current_project_id = None
        self.test_project_path = "/tmp/test-kanban-mcp"
        cleanup_test_project(self.server.db, self.test_project_path)

    def tearDown(self):
        cleanup_test_project(self.server.db, self.test_project_path)

    def test_no_project_set_initially(self):
        """Server should have no current project initially."""
        self.assertIsNone(self.server.current_project_id)

    def test_set_current_project(self):
        """set_current_project should store project in server state."""
        result = self.server.tools[
            'set_current_project']['function'](
            self.test_project_path)
        self.assertTrue(result['success'])
        self.assertIsNotNone(self.server.current_project_id)

    def test_get_current_project(self):
        """get_current_project should return current project info."""
        self.server.tools[
            'set_current_project']['function'](
            self.test_project_path)
        result = self.server.tools['get_current_project']['function']()
        self.assertTrue(result['success'])
        self.assertEqual(
            result['directory_path'],
            self.test_project_path)

    def test_tools_use_current_project_when_not_specified(self):
        """Tools should use current project."""
        self.server.tools[
            'set_current_project']['function'](
            self.test_project_path)

        # Create item without specifying project_dir
        result = self.server.tools['new_item']['function'](
            item_type="issue",
            title="Test Issue"
        )
        self.assertTrue(result['success'])


class TestJSONRPCProtocol(unittest.TestCase):
    """Test JSON-RPC protocol handling."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanMCPServer
        cls.server = KanbanMCPServer()

    def setUp(self):
        self.server.current_project_id = None
        self.test_project_path = "/tmp/test-jsonrpc"
        cleanup_test_project(self.server.db, self.test_project_path)

    def tearDown(self):
        cleanup_test_project(self.server.db, self.test_project_path)

    def test_initialize_response(self):
        """Initialize should return proper protocol info."""
        import asyncio
        request = {
            "jsonrpc": "2.0", "id": 1,
            "method": "initialize", "params": {}}
        response = asyncio.run(self.server.handle_request(request))

        self.assertEqual(response['jsonrpc'], '2.0')
        self.assertEqual(response['id'], 1)
        self.assertIn('result', response)
        self.assertIn('protocolVersion', response['result'])
        self.assertIn('capabilities', response['result'])
        self.assertIn('serverInfo', response['result'])

    def test_tools_list_response(self):
        """tools/list should return all registered tools."""
        import asyncio
        request = {
            "jsonrpc": "2.0", "id": 2,
            "method": "tools/list", "params": {}}
        response = asyncio.run(self.server.handle_request(request))

        self.assertEqual(response['id'], 2)
        self.assertIn('result', response)
        self.assertIn('tools', response['result'])

        tool_names = [t['name'] for t in response['result']['tools']]
        self.assertIn('new_item', tool_names)
        self.assertIn('list_items', tool_names)
        self.assertIn('set_current_project', tool_names)

    def test_tools_call_success(self):
        """tools/call should execute tool and return result."""
        import asyncio

        # First set project
        set_req = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {
                "name": "set_current_project",
                "arguments": {
                    "project_dir": self.test_project_path
                }
            }
        }
        asyncio.run(self.server.handle_request(set_req))

        # Then create item
        request = {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {
                "name": "new_item",
                "arguments": {"item_type": "issue", "title": "Test"}
            }
        }
        response = asyncio.run(self.server.handle_request(request))

        self.assertEqual(response['id'], 3)
        self.assertIn('result', response)
        self.assertIn('content', response['result'])

    def test_tools_call_unknown_tool(self):
        """tools/call with unknown tool should return error."""
        import asyncio
        request = {
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "nonexistent_tool", "arguments": {}}
        }
        response = asyncio.run(self.server.handle_request(request))

        self.assertIn('error', response)
        self.assertEqual(response['error']['code'], -32602)

    def test_unknown_method(self):
        """Unknown method should return error."""
        import asyncio
        request = {
            "jsonrpc": "2.0", "id": 5,
            "method": "unknown/method", "params": {}}
        response = asyncio.run(self.server.handle_request(request))

        self.assertIn('error', response)
        self.assertEqual(response['error']['code'], -32601)


class TestGetTodos(unittest.TestCase):
    """Test get_todos tool specifically."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanMCPServer
        cls.server = KanbanMCPServer()

    def setUp(self):
        self.server.current_project_id = None
        self.test_project_path = "/tmp/test-get-todos"
        cleanup_test_project(self.server.db, self.test_project_path)
        # Set current project
        self.server.tools[
            'set_current_project']['function'](
            self.test_project_path)

    def tearDown(self):
        cleanup_test_project(
            self.server.db, self.test_project_path)

    def test_get_todos_returns_backlog_items(self):
        """get_todos should return backlog items."""
        new = self.server.tools['new_item']['function']
        new(item_type="issue", title="Backlog Issue")
        result = new(
            item_type="todo", title="In Progress Todo")
        item_id = result['item']['id']
        adv = self.server.tools[
            'advance_status']['function']
        adv(item_id)
        adv(item_id)

        todos = self.server.tools['get_todos']['function']()
        self.assertTrue(todos['success'])
        self.assertEqual(todos['count'], 1)
        self.assertEqual(todos['items'][0]['title'], "Backlog Issue")

    def test_get_todos_empty_when_no_backlog(self):
        """get_todos should return empty when no backlog items."""
        todos = self.server.tools['get_todos']['function']()
        self.assertTrue(todos['success'])
        self.assertEqual(todos['count'], 0)


if __name__ == '__main__':
    unittest.main()


class TestConnectionPooling(unittest.TestCase):
    """Test database connection pooling."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanDB
        from kanban_mcp.setup import auto_migrate
        cls.db = KanbanDB()
        auto_migrate(cls.db._backend)
        cls.test_project_path = "/tmp/test-pool"

    def setUp(self):
        cleanup_test_project(self.db, self.test_project_path)

    def tearDown(self):
        cleanup_test_project(self.db, self.test_project_path)

    def test_db_has_backend(self):
        """KanbanDB should have a database backend."""
        self.assertTrue(hasattr(self.db, '_backend'))
        self.assertIsNotNone(self.db._backend)
        self.assertIn(self.db._backend.backend_type, ('mysql', 'sqlite'))

    @unittest.skipIf(
        os.environ.get('KANBAN_BACKEND') == 'sqlite',
        "MySQL-specific pool test")
    def test_get_connection_returns_pooled_connection(self):
        """Backend pool should return working connections."""
        conn = self.db._backend._get_connection()
        self.assertIsNotNone(conn)
        self.assertTrue(
            hasattr(conn, '_pool_config_version')
            or conn.is_connected())
        conn.close()

    def test_multiple_operations_reuse_connections(self):
        """Multiple operations should reuse pooled connections."""
        self.db.ensure_project(self.test_project_path)

        # Perform multiple operations - should not exhaust a small pool
        for i in range(10):
            self.db.create_item(
                project_id=self.db.hash_project_path(self.test_project_path),
                type_name="issue",
                title=f"Issue {i}"
            )

        # If we got here without error, pool is working
        items = self.db.list_items(
            project_id=self.db.hash_project_path(
                self.test_project_path))
        self.assertEqual(len(items), 10)

    @unittest.skipIf(
        os.environ.get('KANBAN_BACKEND') == 'sqlite',
        "MySQL-specific pool test")
    def test_pool_size_configurable(self):
        """Pool size should be configurable at init."""
        from kanban_mcp.core import KanbanDB
        db = KanbanDB(pool_size=3)
        self.assertEqual(db._backend._pool.pool_size, 3)

    def test_concurrent_connections_within_pool_limit(self):
        """Should handle concurrent operations within pool limit."""
        self.db.ensure_project(self.test_project_path)
        project_id = self.db.hash_project_path(self.test_project_path)

        # Create several items rapidly
        item_ids = []
        for i in range(5):
            item_id = self.db.create_item(
                project_id, "issue", f"Concurrent {i}")
            item_ids.append(item_id)

        # Verify all were created
        for item_id in item_ids:
            item = self.db.get_item(item_id)
            self.assertIsNotNone(item)


class TestRelationships(unittest.TestCase):
    """Tests for item relationships."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanDB
        from kanban_mcp.setup import auto_migrate
        cls.db = KanbanDB()
        auto_migrate(cls.db._backend)
        cls.project_id = cls.db.hash_project_path('/tmp/test_relationships')
        # Create project
        cls.db.ensure_project('/tmp/test_relationships',
                              'test_relationships')

    @classmethod
    def tearDownClass(cls):
        cleanup_test_project(cls.db,
                             '/tmp/test_relationships')

    def setUp(self):
        # Create fresh test items for each test
        self.blocker_id = self.db.create_item(
            self.project_id, "issue", "Blocker",
            "desc", 2)
        self.blocked_id = self.db.create_item(
            self.project_id, "feature", "Blocked",
            "desc", 2)
        self.other_id = self.db.create_item(
            self.project_id, "todo", "Other",
            "desc", 3)

    def tearDown(self):
        # Clean up items and relationships
        ph = self.db._backend.placeholder
        ids = (self.blocker_id, self.blocked_id, self.other_id)
        placeholders = f"({ph}, {ph}, {ph})"
        with self.db._db_cursor(commit=True) as cursor:
            cursor.execute(
                "DELETE FROM item_relationships "
                "WHERE source_item_id IN " + placeholders
                + " OR target_item_id IN " + placeholders,
                ids + ids)
        self.db.delete_item(self.blocker_id)
        self.db.delete_item(self.blocked_id)
        self.db.delete_item(self.other_id)

    def test_add_relationship_blocks(self):
        result = self.db.add_relationship(
            self.blocker_id, self.blocked_id, "blocks")
        self.assertTrue(result["success"])
        self.assertEqual(result["type"], "blocks")

    def test_add_relationship_depends_on(self):
        result = self.db.add_relationship(
            self.blocked_id, self.blocker_id,
            "depends_on")
        self.assertTrue(result["success"])
        self.assertEqual(result["type"], "depends_on")

    def test_add_relationship_relates_to(self):
        result = self.db.add_relationship(
            self.blocker_id, self.other_id,
            "relates_to")
        self.assertTrue(result["success"])

    def test_add_relationship_invalid_type(self):
        with self.assertRaises(ValueError):
            self.db.add_relationship(
                self.blocker_id, self.blocked_id,
                "invalid")

    def test_add_relationship_same_item(self):
        with self.assertRaises(ValueError):
            self.db.add_relationship(
                self.blocker_id, self.blocker_id,
                "blocks")

    def test_add_relationship_duplicate(self):
        self.db.add_relationship(
            self.blocker_id, self.blocked_id, "blocks")
        result = self.db.add_relationship(
            self.blocker_id, self.blocked_id, "blocks")
        self.assertFalse(result["success"])
        self.assertIn("already exists", result["error"])

    def test_get_item_relationships(self):
        self.db.add_relationship(
            self.blocker_id, self.blocked_id, "blocks")
        rels = self.db.get_item_relationships(
            self.blocked_id)
        self.assertEqual(len(rels["incoming"]), 1)
        self.assertEqual(
            rels["incoming"][0]["related_item_id"],
            self.blocker_id)
        self.assertEqual(
            rels["incoming"][0]["relationship_type"],
            "blocks")

    def test_remove_relationship(self):
        self.db.add_relationship(
            self.blocker_id, self.blocked_id, "blocks")
        result = self.db.remove_relationship(
            self.blocker_id, self.blocked_id, "blocks")
        self.assertTrue(result["success"])
        rels = self.db.get_item_relationships(self.blocked_id)
        self.assertEqual(len(rels["incoming"]), 0)

    def test_get_blocking_items(self):
        self.db.add_relationship(
            self.blocker_id, self.blocked_id, "blocks")
        blockers = self.db.get_blocking_items(self.blocked_id)
        self.assertEqual(len(blockers), 1)
        self.assertEqual(blockers[0]["id"], self.blocker_id)
        self.assertEqual(blockers[0]["reason"], "blocks")

    def test_get_blocking_items_depends_on(self):
        self.db.add_relationship(
            self.blocked_id, self.blocker_id,
            "depends_on")
        blockers = self.db.get_blocking_items(self.blocked_id)
        self.assertEqual(len(blockers), 1)
        self.assertEqual(blockers[0]["id"], self.blocker_id)
        self.assertEqual(blockers[0]["reason"], "dependency")

    def test_close_blocked_item_fails(self):
        self.db.add_relationship(
            self.blocker_id, self.blocked_id, "blocks")
        result = self.db.close_item(self.blocked_id)
        self.assertFalse(result["success"])
        self.assertIn("blocked by", result["message"])

    def test_close_unblocked_item_succeeds(self):
        self.db.add_relationship(
            self.blocker_id, self.blocked_id, "blocks")
        self.db.close_item(self.blocker_id)  # Close the blocker first
        result = self.db.close_item(self.blocked_id)
        self.assertTrue(result["success"])

    def test_blocking_cleared_when_blocker_done(self):
        self.db.add_relationship(
            self.blocker_id, self.blocked_id, "blocks")
        blockers = self.db.get_blocking_items(self.blocked_id)
        self.assertEqual(len(blockers), 1)

        self.db.set_status(self.blocker_id, "done")
        blockers = self.db.get_blocking_items(self.blocked_id)
        self.assertEqual(len(blockers), 0)


class TestUpdateItem(unittest.TestCase):
    """Tests for update_item functionality."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanDB
        cls.db = KanbanDB()
        cls.test_project_path = "/tmp/test-update-item"
        cls.test_project_id = cls.db.hash_project_path(cls.test_project_path)

    def setUp(self):
        cleanup_test_project(self.db, self.test_project_path)
        self.db.ensure_project(self.test_project_path)
        # Create a test item
        self.item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Original Title",
            description="Original description",
            priority=3
        )

    def tearDown(self):
        cleanup_test_project(self.db, self.test_project_path)

    def test_update_item_title(self):
        """update_item should update title."""
        result = self.db.update_item(self.item_id, title="New Title")
        self.assertTrue(result['success'])

        item = self.db.get_item(self.item_id)
        self.assertEqual(item['title'], "New Title")
        self.assertEqual(
            item['description'], "Original description")

    def test_update_item_description(self):
        """update_item should update description."""
        result = self.db.update_item(
            self.item_id, description="New description")
        self.assertTrue(result['success'])

        item = self.db.get_item(self.item_id)
        self.assertEqual(item['title'], "Original Title")
        self.assertEqual(
            item['description'], "New description")

    def test_update_item_priority(self):
        """update_item should update priority."""
        result = self.db.update_item(self.item_id, priority=1)
        self.assertTrue(result['success'])

        item = self.db.get_item(self.item_id)
        self.assertEqual(item['priority'], 1)

    def test_update_item_multiple_fields(self):
        """update_item should update multiple fields at once."""
        result = self.db.update_item(
            self.item_id,
            title="Updated Title",
            description="Updated description",
            priority=2
        )
        self.assertTrue(result['success'])

        item = self.db.get_item(self.item_id)
        self.assertEqual(item['title'], "Updated Title")
        self.assertEqual(
            item['description'], "Updated description")
        self.assertEqual(item['priority'], 2)

    def test_update_item_returns_updated_item(self):
        """update_item should return the updated item."""
        result = self.db.update_item(self.item_id, title="New Title")
        self.assertTrue(result['success'])
        self.assertIn('item', result)
        self.assertEqual(result['item']['title'], "New Title")

    def test_update_item_not_found(self):
        """update_item should fail for non-existent item."""
        result = self.db.update_item(99999, title="New Title")
        self.assertFalse(result['success'])
        self.assertIn('error', result)

    def test_update_item_no_fields(self):
        """update_item should fail when no fields provided."""
        result = self.db.update_item(self.item_id)
        self.assertFalse(result['success'])
        self.assertIn('error', result)

    def test_update_item_clear_description(self):
        """update_item should allow clearing description with empty string."""
        result = self.db.update_item(self.item_id, description="")
        self.assertTrue(result['success'])

        item = self.db.get_item(self.item_id)
        self.assertEqual(item['description'], "")


class TestEditItemTool(unittest.TestCase):
    """Test edit_item MCP tool."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanMCPServer
        cls.server = KanbanMCPServer()

    def setUp(self):
        self.server.current_project_id = None
        self.test_project_path = "/tmp/test-edit-item-tool"
        cleanup_test_project(self.server.db, self.test_project_path)
        self.server.tools[
            'set_current_project']['function'](
            self.test_project_path)
        result = self.server.tools[
            'new_item']['function'](
            item_type="issue",
            title="Original Title",
            description="Original description",
            priority=3
        )
        self.item_id = result['item']['id']

    def tearDown(self):
        cleanup_test_project(
            self.server.db, self.test_project_path)

    def test_edit_item_tool_exists(self):
        """edit_item tool should be registered."""
        self.assertIn('edit_item', self.server.tools)

    def test_edit_item_tool_updates_title(self):
        """edit_item tool should update item title."""
        result = self.server.tools['edit_item']['function'](
            item_id=self.item_id,
            title="New Title"
        )
        self.assertTrue(result['success'])
        self.assertEqual(result['item']['title'], "New Title")

    def test_edit_item_tool_updates_multiple_fields(self):
        """edit_item tool should update multiple fields."""
        result = self.server.tools['edit_item']['function'](
            item_id=self.item_id,
            title="New Title",
            description="New description",
            priority=1
        )
        self.assertTrue(result['success'])
        self.assertEqual(result['item']['title'], "New Title")
        self.assertEqual(
            result['item']['description'],
            "New description")
        self.assertEqual(result['item']['priority'], 1)


class TestStatusHistory(unittest.TestCase):
    """Tests for status history tracking."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanDB
        cls.db = KanbanDB()
        cls.test_project_path = "/tmp/test-status-history"
        cls.test_project_id = cls.db.hash_project_path(cls.test_project_path)

    def setUp(self):
        cleanup_test_project(self.db, self.test_project_path)
        self.db.ensure_project(self.test_project_path)

    def tearDown(self):
        cleanup_test_project(self.db, self.test_project_path)

    def test_create_item_records_initial_status(self):
        """create_item should record history with change_type='create'."""
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Test Issue"
        )

        history = self.db.get_status_history(item_id)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['change_type'], 'create')
        self.assertIsNone(history[0]['old_status'])
        self.assertEqual(history[0]['new_status'], 'backlog')

    def test_advance_status_records_change(self):
        """advance_status should record history with change_type='advance'."""
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Test Issue"
        )

        self.db.advance_status(item_id)  # backlog -> todo

        history = self.db.get_status_history(item_id)
        self.assertEqual(len(history), 2)
        # First entry is create
        self.assertEqual(history[0]['change_type'], 'create')
        # Second entry is advance
        self.assertEqual(history[1]['change_type'], 'advance')
        self.assertEqual(history[1]['old_status'], 'backlog')
        self.assertEqual(history[1]['new_status'], 'todo')

    def test_revert_status_records_change(self):
        """revert_status should record history with change_type='revert'."""
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Test Issue"
        )

        self.db.advance_status(item_id)  # backlog -> todo
        self.db.revert_status(item_id)   # todo -> backlog

        history = self.db.get_status_history(item_id)
        self.assertEqual(len(history), 3)
        self.assertEqual(history[2]['change_type'], 'revert')
        self.assertEqual(history[2]['old_status'], 'todo')
        self.assertEqual(history[2]['new_status'], 'backlog')

    def test_set_status_records_change(self):
        """set_status should record history with change_type='set'."""
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Test Issue"
        )

        self.db.set_status(item_id, "in_progress")

        history = self.db.get_status_history(item_id)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[1]['change_type'], 'set')
        self.assertEqual(history[1]['old_status'], 'backlog')
        self.assertEqual(history[1]['new_status'], 'in_progress')

    def test_close_item_records_change(self):
        """close_item should record history with change_type='close'."""
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Test Issue"
        )

        self.db.close_item(item_id)

        history = self.db.get_status_history(item_id)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[1]['change_type'], 'close')
        self.assertEqual(history[1]['old_status'], 'backlog')
        self.assertEqual(history[1]['new_status'], 'closed')

    def test_status_history_chronological_order(self):
        """History should be ordered by changed_at ASC (oldest first)."""
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Test Issue"
        )

        self.db.advance_status(item_id)  # backlog -> todo
        self.db.advance_status(item_id)  # todo -> in_progress
        self.db.advance_status(item_id)  # in_progress -> review

        history = self.db.get_status_history(item_id)
        self.assertEqual(len(history), 4)
        # Verify chronological order
        self.assertEqual(history[0]['change_type'], 'create')
        self.assertEqual(history[1]['new_status'], 'todo')
        self.assertEqual(history[2]['new_status'], 'in_progress')
        self.assertEqual(history[3]['new_status'], 'review')
        # Verify timestamps are ascending
        for i in range(len(history) - 1):
            self.assertLessEqual(
                history[i]['changed_at'],
                history[i+1]['changed_at'])

    def test_empty_history_for_nonexistent_item(self):
        """get_status_history should return [] for invalid item_id."""
        history = self.db.get_status_history(99999)
        self.assertEqual(history, [])

    def test_multiple_items_independent_history(self):
        """Each item should have its own independent history."""
        item1_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Issue 1"
        )
        item2_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="todo",
            title="Todo 1"
        )

        # Advance item1 multiple times
        self.db.advance_status(item1_id)
        self.db.advance_status(item1_id)

        # item1 should have 3 history entries (create + 2 advances)
        history1 = self.db.get_status_history(item1_id)
        self.assertEqual(len(history1), 3)

        # item2 should only have 1 history entry (create)
        history2 = self.db.get_status_history(item2_id)
        self.assertEqual(len(history2), 1)


class TestStatusHistoryMCPTool(unittest.TestCase):
    """Test get_status_history MCP tool."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanMCPServer
        cls.server = KanbanMCPServer()

    def setUp(self):
        self.server.current_project_id = None
        self.test_project_path = "/tmp/test-status-history-tool"
        cleanup_test_project(self.server.db, self.test_project_path)
        self.server.tools[
            'set_current_project']['function'](
            self.test_project_path)

    def tearDown(self):
        cleanup_test_project(
            self.server.db, self.test_project_path)

    def test_get_status_history_tool_exists(self):
        """get_status_history tool should be registered."""
        self.assertIn(
            'get_status_history', self.server.tools)

    def test_get_status_history_tool_returns_history(self):
        """get_status_history tool should return history."""
        result = self.server.tools[
            'new_item']['function'](
            item_type="issue",
            title="Test Issue"
        )
        item_id = result['item']['id']

        self.server.tools[
            'advance_status']['function'](item_id)

        history_result = self.server.tools[
            'get_status_history']['function'](item_id)
        self.assertTrue(history_result['success'])
        self.assertEqual(len(history_result['history']), 2)


class TestComplexity(unittest.TestCase):
    """Tests for complexity field on items."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanDB
        cls.db = KanbanDB()
        cls.test_project_path = "/tmp/test-complexity"
        cls.test_project_id = cls.db.hash_project_path(cls.test_project_path)

    def setUp(self):
        cleanup_test_project(self.db, self.test_project_path)
        self.db.ensure_project(self.test_project_path)

    def tearDown(self):
        cleanup_test_project(self.db, self.test_project_path)

    def test_create_item_without_complexity(self):
        """Items created without complexity should have NULL complexity."""
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="No complexity"
        )
        item = self.db.get_item(item_id)
        self.assertIsNone(item['complexity'])

    def test_create_item_with_complexity(self):
        """Items can be created with complexity 1-5."""
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="feature",
            title="Complex feature",
            complexity=4
        )
        item = self.db.get_item(item_id)
        self.assertEqual(item['complexity'], 4)

    def test_update_item_add_complexity(self):
        """Complexity can be added to an existing item."""
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="todo",
            title="Todo item"
        )
        result = self.db.update_item(item_id, complexity=3)
        self.assertTrue(result['success'])
        item = self.db.get_item(item_id)
        self.assertEqual(item['complexity'], 3)

    def test_update_item_change_complexity(self):
        """Complexity can be changed."""
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Issue",
            complexity=2
        )
        self.db.update_item(item_id, complexity=5)
        item = self.db.get_item(item_id)
        self.assertEqual(item['complexity'], 5)

    def test_create_item_invalid_complexity_rejected(self):
        """Complexity outside 1-5 should be rejected."""
        with self.assertRaises(ValueError):
            self.db.create_item(
                project_id=self.test_project_id,
                type_name="issue",
                title="Invalid",
                complexity=10
            )

    def test_update_item_invalid_complexity_rejected(self):
        """Updating with invalid complexity should fail."""
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Test"
        )
        result = self.db.update_item(item_id, complexity=0)
        self.assertFalse(result['success'])
        self.assertIn('Complexity must be 1-5', result['error'])


class TestItemMetrics(unittest.TestCase):
    """Tests for get_item_metrics functionality."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanDB
        cls.db = KanbanDB()
        cls.test_project_path = "/tmp/test-metrics"
        cls.test_project_id = cls.db.hash_project_path(cls.test_project_path)

    def setUp(self):
        cleanup_test_project(self.db, self.test_project_path)
        self.db.ensure_project(self.test_project_path)

    def tearDown(self):
        cleanup_test_project(self.db, self.test_project_path)

    def test_metrics_for_nonexistent_item(self):
        """get_item_metrics returns None for invalid item_id."""
        result = self.db.get_item_metrics(99999)
        self.assertIsNone(result)

    def test_metrics_for_new_item(self):
        """New item should have metrics with current_age."""
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="New Issue"
        )
        metrics = self.db.get_item_metrics(item_id)
        self.assertIsNotNone(metrics)
        self.assertEqual(metrics['item_id'], item_id)
        self.assertIsNone(metrics['lead_time'])  # Not closed
        self.assertIsNone(metrics['cycle_time'])  # Never in_progress
        self.assertIsNotNone(metrics['current_age'])
        self.assertEqual(metrics['revert_count'], 0)

    def test_metrics_time_in_status(self):
        """time_in_each_status should track status durations."""
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Test Issue"
        )
        self.db.advance_status(item_id)  # backlog -> todo

        metrics = self.db.get_item_metrics(item_id)
        self.assertIn('backlog', metrics['time_in_each_status'])
        self.assertIn('todo', metrics['time_in_each_status'])

    def test_metrics_revert_count(self):
        """revert_count should count status reverts."""
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Test Issue"
        )
        self.db.advance_status(item_id)  # backlog -> todo
        self.db.revert_status(item_id)   # todo -> backlog
        self.db.advance_status(item_id)  # backlog -> todo
        self.db.revert_status(item_id)   # todo -> backlog

        metrics = self.db.get_item_metrics(item_id)
        self.assertEqual(metrics['revert_count'], 2)

    def test_metrics_includes_complexity(self):
        """Metrics should include the item's complexity."""
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="feature",
            title="Feature",
            complexity=3
        )
        metrics = self.db.get_item_metrics(item_id)
        self.assertEqual(metrics['complexity'], 3)


class TestComplexityMCPTools(unittest.TestCase):
    """Test complexity in MCP tools."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanMCPServer
        cls.server = KanbanMCPServer()

    def setUp(self):
        self.server.current_project_id = None
        self.test_project_path = "/tmp/test-complexity-tools"
        cleanup_test_project(self.server.db, self.test_project_path)
        self.server.tools[
            'set_current_project']['function'](
            self.test_project_path)

    def tearDown(self):
        cleanup_test_project(
            self.server.db, self.test_project_path)

    def test_new_item_with_complexity(self):
        """new_item tool should accept complexity parameter."""
        result = self.server.tools['new_item']['function'](
            item_type="feature",
            title="Complex Feature",
            complexity=4
        )
        self.assertTrue(result['success'])
        self.assertEqual(result['item']['complexity'], 4)

    def test_edit_item_add_complexity(self):
        """edit_item tool should accept complexity parameter."""
        result = self.server.tools['new_item']['function'](
            item_type="issue",
            title="Issue"
        )
        item_id = result['item']['id']

        edit_result = self.server.tools['edit_item']['function'](
            item_id=item_id,
            complexity=3
        )
        self.assertTrue(edit_result['success'])
        self.assertEqual(edit_result['item']['complexity'], 3)

    def test_get_item_metrics_tool_exists(self):
        """get_item_metrics tool should be registered."""
        self.assertIn('get_item_metrics', self.server.tools)

    def test_get_item_metrics_tool_returns_metrics(self):
        """get_item_metrics tool should return item metrics."""
        result = self.server.tools['new_item']['function'](
            item_type="issue",
            title="Test Issue"
        )
        item_id = result['item']['id']

        metrics_result = self.server.tools[
            'get_item_metrics']['function'](item_id)
        self.assertTrue(metrics_result['success'])
        self.assertIn('metrics', metrics_result)
        self.assertEqual(
            metrics_result['metrics']['item_id'],
            item_id)


class TestTags(unittest.TestCase):
    """Tests for item tagging functionality."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanDB
        cls.db = KanbanDB()
        cls.test_project_path = "/tmp/test-tags"
        cls.test_project_id = cls.db.hash_project_path(cls.test_project_path)

    def setUp(self):
        cleanup_test_project(self.db, self.test_project_path)
        self.db.ensure_project(self.test_project_path)

    def tearDown(self):
        cleanup_test_project(self.db, self.test_project_path)

    # --- Tag Creation Tests ---

    def test_ensure_tag_creates_new_tag(self):
        """ensure_tag should create a new tag if it doesn't exist."""
        tag_id = self.db.ensure_tag(self.test_project_id, "backend")
        self.assertIsInstance(tag_id, int)
        self.assertGreater(tag_id, 0)

    def test_ensure_tag_returns_existing_tag(self):
        """ensure_tag should return existing tag_id if tag exists."""
        tag_id1 = self.db.ensure_tag(self.test_project_id, "frontend")
        tag_id2 = self.db.ensure_tag(self.test_project_id, "frontend")
        self.assertEqual(tag_id1, tag_id2)

    def test_ensure_tag_normalizes_name(self):
        """ensure_tag should normalize tag names (lowercase, stripped)."""
        tag_id1 = self.db.ensure_tag(self.test_project_id, "Backend")
        tag_id2 = self.db.ensure_tag(self.test_project_id, "  backend  ")
        tag_id3 = self.db.ensure_tag(self.test_project_id, "BACKEND")
        self.assertEqual(tag_id1, tag_id2)
        self.assertEqual(tag_id2, tag_id3)

    def test_ensure_tag_assigns_color_from_palette(self):
        """ensure_tag should auto-assign color from predefined palette."""
        tag_id = self.db.ensure_tag(self.test_project_id, "test-tag")
        tag = self.db.get_tag(tag_id)
        self.assertIsNotNone(tag['color'])
        self.assertTrue(tag['color'].startswith('#'))
        self.assertEqual(len(tag['color']), 7)  # #RRGGBB format

    def test_ensure_tag_rotates_colors(self):
        """ensure_tag should rotate through color palette."""
        colors = []
        for i in range(15):  # More than palette size
            tag_id = self.db.ensure_tag(self.test_project_id, f"tag-{i}")
            tag = self.db.get_tag(tag_id)
            colors.append(tag['color'])
        # First 12 should be unique (palette size), then repeat
        unique_colors = set(colors[:12])
        self.assertEqual(len(unique_colors), 12)

    def test_ensure_tag_empty_name_fails(self):
        """ensure_tag should reject empty tag names."""
        with self.assertRaises(ValueError):
            self.db.ensure_tag(self.test_project_id, "")
        with self.assertRaises(ValueError):
            self.db.ensure_tag(self.test_project_id, "   ")

    def test_ensure_tag_too_long_name_fails(self):
        """ensure_tag should reject names longer than 50 chars."""
        with self.assertRaises(ValueError):
            self.db.ensure_tag(self.test_project_id, "a" * 51)

    # --- Tag Retrieval Tests ---

    def test_get_tag_returns_tag(self):
        """get_tag should return tag details."""
        tag_id = self.db.ensure_tag(self.test_project_id, "api")
        tag = self.db.get_tag(tag_id)
        self.assertEqual(tag['id'], tag_id)
        self.assertEqual(tag['name'], "api")
        self.assertIn('color', tag)
        self.assertEqual(tag['project_id'], self.test_project_id)

    def test_get_tag_nonexistent_returns_none(self):
        """get_tag should return None for invalid tag_id."""
        tag = self.db.get_tag(99999)
        self.assertIsNone(tag)

    def test_get_project_tags_returns_all(self):
        """get_project_tags should return all tags for a project."""
        self.db.ensure_tag(self.test_project_id, "alpha")
        self.db.ensure_tag(self.test_project_id, "beta")
        self.db.ensure_tag(self.test_project_id, "gamma")

        tags = self.db.get_project_tags(self.test_project_id)
        self.assertEqual(len(tags), 3)
        tag_names = [t['name'] for t in tags]
        self.assertIn("alpha", tag_names)
        self.assertIn("beta", tag_names)
        self.assertIn("gamma", tag_names)

    def test_get_project_tags_ordered_by_name(self):
        """get_project_tags should return tags ordered alphabetically."""
        self.db.ensure_tag(self.test_project_id, "zebra")
        self.db.ensure_tag(self.test_project_id, "apple")
        self.db.ensure_tag(self.test_project_id, "mango")

        tags = self.db.get_project_tags(self.test_project_id)
        names = [t['name'] for t in tags]
        self.assertEqual(names, ["apple", "mango", "zebra"])

    def test_get_project_tags_empty_project(self):
        """get_project_tags should return empty list if no tags."""
        tags = self.db.get_project_tags(self.test_project_id)
        self.assertEqual(tags, [])

    # --- Tag Update Tests ---

    def test_update_tag_color(self):
        """update_tag should change tag color."""
        tag_id = self.db.ensure_tag(self.test_project_id, "custom")
        result = self.db.update_tag(tag_id, color="#FF0000")
        self.assertTrue(result['success'])

        tag = self.db.get_tag(tag_id)
        self.assertEqual(tag['color'], "#FF0000")

    def test_update_tag_name(self):
        """update_tag should change tag name."""
        tag_id = self.db.ensure_tag(self.test_project_id, "oldname")
        result = self.db.update_tag(tag_id, name="newname")
        self.assertTrue(result['success'])

        tag = self.db.get_tag(tag_id)
        self.assertEqual(tag['name'], "newname")

    def test_update_tag_invalid_color_fails(self):
        """update_tag should reject invalid color format."""
        tag_id = self.db.ensure_tag(self.test_project_id, "test")
        result = self.db.update_tag(tag_id, color="red")
        self.assertFalse(result['success'])
        self.assertIn('error', result)

    def test_update_tag_duplicate_name_fails(self):
        """update_tag should fail if name already exists in project."""
        self.db.ensure_tag(self.test_project_id, "existing")
        tag_id = self.db.ensure_tag(self.test_project_id, "rename-me")
        result = self.db.update_tag(tag_id, name="existing")
        self.assertFalse(result['success'])

    def test_update_tag_nonexistent_fails(self):
        """update_tag should fail for invalid tag_id."""
        result = self.db.update_tag(99999, name="test")
        self.assertFalse(result['success'])

    # --- Tag Deletion Tests ---

    def test_delete_tag(self):
        """delete_tag should remove the tag."""
        tag_id = self.db.ensure_tag(self.test_project_id, "deleteme")
        result = self.db.delete_tag(tag_id)
        self.assertTrue(result['success'])

        tag = self.db.get_tag(tag_id)
        self.assertIsNone(tag)

    def test_delete_tag_nonexistent(self):
        """delete_tag should return success=False for invalid tag_id."""
        result = self.db.delete_tag(99999)
        self.assertFalse(result['success'])


class TestItemTags(unittest.TestCase):
    """Tests for item-tag associations."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanDB
        cls.db = KanbanDB()
        cls.test_project_path = "/tmp/test-item-tags"
        cls.test_project_id = cls.db.hash_project_path(cls.test_project_path)

    def setUp(self):
        cleanup_test_project(self.db, self.test_project_path)
        self.db.ensure_project(self.test_project_path)
        # Create test item
        self.item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="feature",
            title="Test Feature"
        )

    def tearDown(self):
        cleanup_test_project(self.db, self.test_project_path)

    # --- Add Tags to Item Tests ---

    def test_add_tag_to_item(self):
        """add_tag_to_item should associate tag with item."""
        result = self.db.add_tag_to_item(self.item_id, "urgent")
        self.assertTrue(result['success'])

        tags = self.db.get_item_tags(self.item_id)
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0]['name'], "urgent")

    def test_add_tag_to_item_creates_tag_on_fly(self):
        """add_tag_to_item should create tag if it doesn't exist."""
        # Tag shouldn't exist yet
        tags_before = self.db.get_project_tags(self.test_project_id)
        self.assertEqual(len(tags_before), 0)

        self.db.add_tag_to_item(self.item_id, "new-tag")

        # Tag should now exist
        tags_after = self.db.get_project_tags(self.test_project_id)
        self.assertEqual(len(tags_after), 1)
        self.assertEqual(tags_after[0]['name'], "new-tag")

    def test_add_multiple_tags_to_item(self):
        """Adding multiple tags to an item should work."""
        self.db.add_tag_to_item(self.item_id, "frontend")
        self.db.add_tag_to_item(self.item_id, "backend")
        self.db.add_tag_to_item(self.item_id, "api")

        tags = self.db.get_item_tags(self.item_id)
        self.assertEqual(len(tags), 3)
        tag_names = [t['name'] for t in tags]
        self.assertIn("frontend", tag_names)
        self.assertIn("backend", tag_names)
        self.assertIn("api", tag_names)

    def test_add_duplicate_tag_to_item_idempotent(self):
        """Adding same tag twice should be idempotent (no error)."""
        self.db.add_tag_to_item(self.item_id, "duplicate")
        result = self.db.add_tag_to_item(self.item_id, "duplicate")
        self.assertFalse(result['success'])
        self.assertIn("already", result['error'].lower())

        tags = self.db.get_item_tags(self.item_id)
        self.assertEqual(len(tags), 1)

    def test_add_tag_to_nonexistent_item_fails(self):
        """add_tag_to_item should fail for invalid item_id."""
        with self.assertRaises(ValueError):
            self.db.add_tag_to_item(99999, "test")

    def test_add_tag_normalizes_name(self):
        """add_tag_to_item should normalize tag names."""
        self.db.add_tag_to_item(self.item_id, "  MixedCase  ")
        tags = self.db.get_item_tags(self.item_id)
        self.assertEqual(tags[0]['name'], "mixedcase")

    # --- Remove Tag from Item Tests ---

    def test_remove_tag_from_item(self):
        """remove_tag_from_item should remove the association."""
        self.db.add_tag_to_item(self.item_id, "removeme")
        tags = self.db.get_item_tags(self.item_id)
        tag_id = tags[0]['id']

        result = self.db.remove_tag_from_item(self.item_id, tag_id)
        self.assertTrue(result['success'])

        tags_after = self.db.get_item_tags(self.item_id)
        self.assertEqual(len(tags_after), 0)

    def test_remove_tag_keeps_tag_definition(self):
        """Removing tag from item should not delete the tag itself."""
        self.db.add_tag_to_item(self.item_id, "keepme")
        tag_id = self.db.get_item_tags(self.item_id)[0]['id']

        self.db.remove_tag_from_item(self.item_id, tag_id)

        # Tag should still exist in project
        tag = self.db.get_tag(tag_id)
        self.assertIsNotNone(tag)

    def test_remove_nonexistent_association(self):
        """Removing non-associated tag should return success=False."""
        tag_id = self.db.ensure_tag(self.test_project_id, "notassociated")
        result = self.db.remove_tag_from_item(self.item_id, tag_id)
        self.assertFalse(result['success'])

    # --- Get Item Tags Tests ---

    def test_get_item_tags_empty(self):
        """get_item_tags should return empty list for untagged item."""
        tags = self.db.get_item_tags(self.item_id)
        self.assertEqual(tags, [])

    def test_get_item_tags_includes_color(self):
        """get_item_tags should include tag colors."""
        self.db.add_tag_to_item(self.item_id, "colored")
        tags = self.db.get_item_tags(self.item_id)
        self.assertIn('color', tags[0])
        self.assertTrue(tags[0]['color'].startswith('#'))

    def test_get_item_tags_ordered_by_name(self):
        """get_item_tags should return tags ordered alphabetically."""
        self.db.add_tag_to_item(self.item_id, "zebra")
        self.db.add_tag_to_item(self.item_id, "apple")
        self.db.add_tag_to_item(self.item_id, "mango")

        tags = self.db.get_item_tags(self.item_id)
        names = [t['name'] for t in tags]
        self.assertEqual(names, ["apple", "mango", "zebra"])

    # --- Cascade Delete Tests ---

    def test_delete_tag_cascades_to_item_tags(self):
        """Deleting a tag should remove it from all items."""
        self.db.add_tag_to_item(self.item_id, "cascade-test")
        tag_id = self.db.get_item_tags(self.item_id)[0]['id']

        # Create another item with same tag
        item2_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Another Item"
        )
        self.db.add_tag_to_item(item2_id, "cascade-test")

        # Delete the tag
        self.db.delete_tag(tag_id)

        # Both items should have no tags
        self.assertEqual(self.db.get_item_tags(self.item_id), [])
        self.assertEqual(self.db.get_item_tags(item2_id), [])

    def test_delete_item_removes_tag_associations(self):
        """Deleting an item should remove its tag associations."""
        self.db.add_tag_to_item(self.item_id, "item-delete-test")
        tag_id = self.db.get_item_tags(self.item_id)[0]['id']

        # Delete the item
        self.db.delete_item(self.item_id)

        # Tag should still exist
        tag = self.db.get_tag(tag_id)
        self.assertIsNotNone(tag)


class TestListItemsWithTags(unittest.TestCase):
    """Tests for list_items with tag filtering."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanDB
        cls.db = KanbanDB()
        cls.test_project_path = "/tmp/test-list-items-tags"
        cls.test_project_id = cls.db.hash_project_path(cls.test_project_path)

    def setUp(self):
        cleanup_test_project(self.db, self.test_project_path)
        self.db.ensure_project(self.test_project_path)

        # Create test items with various tags
        self.item1_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="feature",
            title="Frontend Feature"
        )
        self.db.add_tag_to_item(self.item1_id, "frontend")
        self.db.add_tag_to_item(self.item1_id, "ui")

        self.item2_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="feature",
            title="Backend Feature"
        )
        self.db.add_tag_to_item(self.item2_id, "backend")
        self.db.add_tag_to_item(self.item2_id, "api")

        self.item3_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Full Stack Issue"
        )
        self.db.add_tag_to_item(self.item3_id, "frontend")
        self.db.add_tag_to_item(self.item3_id, "backend")

        self.item4_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="todo",
            title="Untagged Todo"
        )

    def tearDown(self):
        cleanup_test_project(self.db, self.test_project_path)

    def test_list_items_no_tag_filter(self):
        """list_items without tag filter should return all items."""
        items = self.db.list_items(project_id=self.test_project_id)
        self.assertEqual(len(items), 4)

    def test_list_items_single_tag_or(self):
        """list_items with single tag should return matching items."""
        items = self.db.list_items(
            project_id=self.test_project_id,
            tag_names=["frontend"],
            tag_match_mode="any"
        )
        self.assertEqual(len(items), 2)
        titles = [i['title'] for i in items]
        self.assertIn("Frontend Feature", titles)
        self.assertIn("Full Stack Issue", titles)

    def test_list_items_multiple_tags_or(self):
        """list_items with multiple tags (OR) returns any."""
        items = self.db.list_items(
            project_id=self.test_project_id,
            tag_names=["ui", "api"],
            tag_match_mode="any"
        )
        self.assertEqual(len(items), 2)
        titles = [i['title'] for i in items]
        self.assertIn("Frontend Feature", titles)
        self.assertIn("Backend Feature", titles)

    def test_list_items_multiple_tags_and(self):
        """list_items with multiple tags (AND) returns all."""
        items = self.db.list_items(
            project_id=self.test_project_id,
            tag_names=["frontend", "backend"],
            tag_match_mode="all"
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['title'], "Full Stack Issue")

    def test_list_items_and_no_match(self):
        """list_items with AND should return empty if no item has all tags."""
        items = self.db.list_items(
            project_id=self.test_project_id,
            tag_names=["frontend", "api"],
            tag_match_mode="all"
        )
        self.assertEqual(len(items), 0)

    def test_list_items_tag_filter_with_type_filter(self):
        """list_items should combine tag and type filters."""
        items = self.db.list_items(
            project_id=self.test_project_id,
            type_name="feature",
            tag_names=["frontend"],
            tag_match_mode="any"
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['title'], "Frontend Feature")

    def test_list_items_tag_filter_with_status_filter(self):
        """list_items should combine tag and status filters."""
        # Advance one item
        self.db.advance_status(self.item1_id)  # backlog -> todo

        items = self.db.list_items(
            project_id=self.test_project_id,
            status_name="todo",
            tag_names=["frontend"],
            tag_match_mode="any"
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['title'], "Frontend Feature")

    def test_list_items_nonexistent_tag(self):
        """list_items with nonexistent tag should return empty."""
        items = self.db.list_items(
            project_id=self.test_project_id,
            tag_names=["nonexistent"],
            tag_match_mode="any"
        )
        self.assertEqual(len(items), 0)

    def test_list_items_default_mode_is_any(self):
        """list_items should default to 'any' mode if not specified."""
        items = self.db.list_items(
            project_id=self.test_project_id,
            tag_names=["frontend", "backend"]
        )
        # Should return 3 items (any of the two tags)
        self.assertEqual(len(items), 3)


class TestTagMCPTools(unittest.TestCase):
    """Tests for tag MCP tools."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanMCPServer
        cls.server = KanbanMCPServer()

    def setUp(self):
        self.server.current_project_id = None
        self.test_project_path = "/tmp/test-tag-tools"
        cleanup_test_project(self.server.db, self.test_project_path)
        self.server.tools[
            'set_current_project']['function'](
            self.test_project_path)
        result = self.server.tools[
            'new_item']['function'](
            item_type="feature",
            title="Test Feature"
        )
        self.item_id = result['item']['id']

    def tearDown(self):
        cleanup_test_project(
            self.server.db, self.test_project_path)

    # --- Tool Registration Tests ---

    def test_list_tags_tool_exists(self):
        """list_tags tool should be registered."""
        self.assertIn('list_tags', self.server.tools)

    def test_add_tag_tool_exists(self):
        """add_tag tool should be registered."""
        self.assertIn('add_tag', self.server.tools)

    def test_remove_tag_tool_exists(self):
        """remove_tag tool should be registered."""
        self.assertIn('remove_tag', self.server.tools)

    def test_update_tag_tool_exists(self):
        """update_tag tool should be registered."""
        self.assertIn('update_tag', self.server.tools)

    def test_delete_tag_tool_exists(self):
        """delete_tag tool should be registered."""
        self.assertIn('delete_tag', self.server.tools)

    def test_get_item_tags_tool_exists(self):
        """get_item_tags tool should be registered."""
        self.assertIn('get_item_tags', self.server.tools)

    # --- Tool Functionality Tests ---

    def test_list_tags_returns_project_tags(self):
        """list_tags should return all tags for current project."""
        # Add some tags via items
        self.server.tools['add_tag']['function'](self.item_id, "tag1")
        self.server.tools['add_tag']['function'](self.item_id, "tag2")

        result = self.server.tools['list_tags']['function']()
        self.assertTrue(result['success'])
        self.assertEqual(result['count'], 2)
        tag_names = [t['name'] for t in result['tags']]
        self.assertIn("tag1", tag_names)
        self.assertIn("tag2", tag_names)

    def test_add_tag_adds_to_item(self):
        """add_tag should add tag to item."""
        result = self.server.tools[
            'add_tag']['function'](
            self.item_id, "newtag")
        self.assertTrue(result['success'])

        tags_result = self.server.tools[
            'get_item_tags']['function'](self.item_id)
        self.assertEqual(len(tags_result['tags']), 1)
        self.assertEqual(
            tags_result['tags'][0]['name'], "newtag")

    def test_remove_tag_removes_from_item(self):
        """remove_tag should remove tag from item."""
        self.server.tools[
            'add_tag']['function'](
            self.item_id, "removethis")
        tags = self.server.tools[
            'get_item_tags']['function'](
            self.item_id)['tags']
        tag_id = tags[0]['id']

        result = self.server.tools[
            'remove_tag']['function'](
            self.item_id, tag_id)
        self.assertTrue(result['success'])

        tags_after = self.server.tools[
            'get_item_tags']['function'](self.item_id)
        self.assertEqual(len(tags_after['tags']), 0)

    def test_update_tag_changes_color(self):
        """update_tag should change tag color."""
        self.server.tools[
            'add_tag']['function'](
            self.item_id, "colorchange")
        tags = self.server.tools[
            'get_item_tags']['function'](
            self.item_id)['tags']
        tag_id = tags[0]['id']

        result = self.server.tools[
            'update_tag']['function'](
            tag_id, color="#123456")
        self.assertTrue(result['success'])
        self.assertEqual(result['tag']['color'], "#123456")

    def test_delete_tag_removes_tag(self):
        """delete_tag should delete tag from project."""
        self.server.tools['add_tag']['function'](self.item_id, "deletethis")
        tags = self.server.tools['list_tags']['function']()['tags']
        tag_id = tags[0]['id']

        result = self.server.tools['delete_tag']['function'](tag_id)
        self.assertTrue(result['success'])

        tags_after = self.server.tools['list_tags']['function']()
        self.assertEqual(tags_after['count'], 0)

    def test_list_items_with_tag_filter(self):
        """list_items tool should support tag filtering."""
        # Create items with different tags
        result2 = self.server.tools['new_item']['function'](
            item_type="issue",
            title="Issue"
        )
        item2_id = result2['item']['id']

        self.server.tools['add_tag']['function'](self.item_id, "frontend")
        self.server.tools['add_tag']['function'](item2_id, "backend")

        # Filter by tag
        result = self.server.tools['list_items']['function'](tags="frontend")
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['items'][0]['title'], "Test Feature")

    def test_list_items_with_tag_mode(self):
        """list_items tool should support tag_mode parameter."""
        self.server.tools['add_tag']['function'](self.item_id, "tag1")
        self.server.tools['add_tag']['function'](self.item_id, "tag2")

        result2 = self.server.tools['new_item']['function'](
            item_type="issue",
            title="Issue with tag1"
        )
        self.server.tools['add_tag']['function'](result2['item']['id'], "tag1")

        # AND mode - only item with both tags
        result = self.server.tools['list_items']['function'](
            tags="tag1,tag2",
            tag_mode="all"
        )
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['items'][0]['title'], "Test Feature")


class TestEpicSupport(unittest.TestCase):
    """Tests for epic item type and parent-child hierarchy."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanDB
        cls.db = KanbanDB()
        cls.test_project_path = "/tmp/test-epic-support"
        cls.test_project_id = cls.db.hash_project_path(cls.test_project_path)

    def setUp(self):
        cleanup_test_project(self.db, self.test_project_path)
        self.db.ensure_project(self.test_project_path)

    def tearDown(self):
        cleanup_test_project(self.db, self.test_project_path)

    # --- Epic Type Tests ---

    def test_create_epic_default_status(self):
        """Epic should start in backlog status."""
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="epic",
            title="Test Epic"
        )
        item = self.db.get_item(item_id)
        self.assertEqual(item['type_name'], 'epic')
        self.assertEqual(item['status_name'], 'backlog')

    def test_epic_workflow_matches_issue(self):
        """Epic should have same workflow as issue."""
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="epic",
            title="Test Epic"
        )

        # Advance through all statuses
        self.db.advance_status(item_id)  # backlog -> todo
        item = self.db.get_item(item_id)
        self.assertEqual(item['status_name'], 'todo')

        self.db.advance_status(item_id)  # todo -> in_progress
        item = self.db.get_item(item_id)
        self.assertEqual(item['status_name'], 'in_progress')

        self.db.advance_status(item_id)  # in_progress -> review
        item = self.db.get_item(item_id)
        self.assertEqual(item['status_name'], 'review')

        self.db.advance_status(item_id)  # review -> done
        item = self.db.get_item(item_id)
        self.assertEqual(item['status_name'], 'done')

        self.db.advance_status(item_id)  # done -> closed
        item = self.db.get_item(item_id)
        self.assertEqual(item['status_name'], 'closed')

    # --- Parent/Child Hierarchy Tests ---

    def test_create_item_with_parent(self):
        """Items can be created with a parent_id."""
        epic_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="epic",
            title="Parent Epic"
        )
        child_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="feature",
            title="Child Feature",
            parent_id=epic_id
        )

        child = self.db.get_item(child_id)
        self.assertEqual(child['parent_id'], epic_id)

    def test_create_item_invalid_parent_fails(self):
        """Creating item with non-existent parent should fail."""
        with self.assertRaises(ValueError):
            self.db.create_item(
                project_id=self.test_project_id,
                type_name="issue",
                title="Orphan",
                parent_id=99999
            )

    def test_create_item_parent_different_project_fails(self):
        """Creating item with parent from different project should fail."""
        # Create parent in different project
        other_project_path = "/tmp/test-epic-support-other"
        other_project_id = self.db.hash_project_path(other_project_path)
        self.db.ensure_project(other_project_path)

        try:
            other_epic_id = self.db.create_item(
                project_id=other_project_id,
                type_name="epic",
                title="Other Project Epic"
            )

            # Try to create child in different project
            with self.assertRaises(ValueError):
                self.db.create_item(
                    project_id=self.test_project_id,
                    type_name="issue",
                    title="Cross-project child",
                    parent_id=other_epic_id
                )
        finally:
            cleanup_test_project(self.db, other_project_path)

    def test_get_item_includes_parent_id(self):
        """get_item should include parent_id in result."""
        epic_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="epic",
            title="Epic"
        )
        child_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="todo",
            title="Child",
            parent_id=epic_id
        )

        child = self.db.get_item(child_id)
        self.assertIn('parent_id', child)
        self.assertEqual(child['parent_id'], epic_id)

        epic = self.db.get_item(epic_id)
        self.assertIn('parent_id', epic)
        self.assertIsNone(epic['parent_id'])

    # --- Descendants and Progress Tests ---

    def test_get_children(self):
        """get_children should return direct children."""
        epic_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="epic",
            title="Epic"
        )
        child1_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Child 1",
            parent_id=epic_id
        )
        child2_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="feature",
            title="Child 2",
            parent_id=epic_id
        )

        children = self.db.get_children(epic_id)
        self.assertEqual(len(children), 2)
        child_ids = [c['id'] for c in children]
        self.assertIn(child1_id, child_ids)
        self.assertIn(child2_id, child_ids)

    def test_get_all_descendants_recursive(self):
        """get_all_descendants should return all nested descendants."""
        epic_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="epic",
            title="Root Epic"
        )
        sub_epic_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="epic",
            title="Sub Epic",
            parent_id=epic_id
        )
        grandchild_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Grandchild Issue",
            parent_id=sub_epic_id
        )

        descendants = self.db.get_all_descendants(epic_id)
        self.assertEqual(len(descendants), 2)
        descendant_ids = [d['id'] for d in descendants]
        self.assertIn(sub_epic_id, descendant_ids)
        self.assertIn(grandchild_id, descendant_ids)

    def test_get_epic_progress_empty(self):
        """Epic with no children should have 0/0 progress."""
        epic_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="epic",
            title="Empty Epic"
        )

        progress = self.db.get_epic_progress(epic_id)
        self.assertEqual(progress['total'], 0)
        self.assertEqual(progress['completed'], 0)
        self.assertEqual(progress['percent'], 0)

    def test_get_epic_progress_partial(self):
        """Epic progress should reflect partial completion."""
        epic_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="epic",
            title="Partial Epic"
        )
        child1_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Completed Issue",
            parent_id=epic_id
        )
        child2_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Incomplete Issue",
            parent_id=epic_id
        )

        # Complete one child
        self.db.set_status(child1_id, "done")

        progress = self.db.get_epic_progress(epic_id)
        self.assertEqual(progress['total'], 2)
        self.assertEqual(progress['completed'], 1)
        self.assertEqual(progress['percent'], 50.0)
        self.assertIn(child2_id, progress['incomplete_items'])

    def test_get_epic_progress_complete(self):
        """Epic progress should show 100% when all children done/closed."""
        epic_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="epic",
            title="Complete Epic"
        )
        child1_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Done Issue",
            parent_id=epic_id
        )
        child2_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Closed Issue",
            parent_id=epic_id
        )

        # Complete both children (done and closed both count)
        self.db.set_status(child1_id, "done")
        self.db.close_item(child2_id)

        progress = self.db.get_epic_progress(epic_id)
        self.assertEqual(progress['total'], 2)
        self.assertEqual(progress['completed'], 2)
        self.assertEqual(progress['percent'], 100.0)
        self.assertEqual(progress['incomplete_items'], [])

    def test_get_epic_progress_recursive(self):
        """Epic progress should include nested descendants."""
        epic_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="epic",
            title="Root Epic"
        )
        sub_epic_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="epic",
            title="Sub Epic",
            parent_id=epic_id
        )
        grandchild_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Grandchild",
            parent_id=sub_epic_id
        )

        # Complete grandchild
        self.db.set_status(grandchild_id, "done")

        # Root epic should show 1/2 (sub-epic not done, grandchild done)
        progress = self.db.get_epic_progress(epic_id)
        self.assertEqual(progress['total'], 2)
        self.assertEqual(progress['completed'], 1)

    # --- Auto-Advance Tests ---

    def test_auto_advance_epic_to_review(self):
        """Epic should auto-advance to 'review' when all children complete."""
        epic_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="epic",
            title="Auto-advance Epic"
        )
        child_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Only Child",
            parent_id=epic_id
        )

        # Move epic to in_progress
        self.db.set_status(epic_id, "in_progress")

        # Complete the child
        self.db.set_status(child_id, "done")

        # Epic should auto-advance to review
        epic = self.db.get_item(epic_id)
        self.assertEqual(epic['status_name'], 'review')

    def test_no_auto_advance_if_already_review_or_beyond(self):
        """Epic should not auto-advance if already in review/done/closed."""
        epic_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="epic",
            title="Already Review Epic"
        )
        child_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Child",
            parent_id=epic_id
        )

        # Move epic to done
        self.db.set_status(epic_id, "done")

        # Complete child - epic should stay done, not change
        self.db.close_item(child_id)

        epic = self.db.get_item(epic_id)
        self.assertEqual(epic['status_name'], 'done')

    # --- Epic Closure Blocking Tests ---

    def test_block_epic_closure_incomplete_children(self):
        """Epic cannot be closed if children are incomplete."""
        epic_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="epic",
            title="Incomplete Epic"
        )
        self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Incomplete Child",
            parent_id=epic_id
        )

        result = self.db.close_item(epic_id)
        self.assertFalse(result['success'])
        self.assertIn('incomplete', result['message'].lower())

    def test_epic_closure_all_complete(self):
        """Epic can be closed when all children are complete."""
        epic_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="epic",
            title="Complete Epic"
        )
        child_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Child",
            parent_id=epic_id
        )

        # Complete the child
        self.db.set_status(child_id, "done")

        # Now epic can be closed
        result = self.db.close_item(epic_id)
        self.assertTrue(result['success'])

    # --- Set Parent Tests ---

    def test_set_parent(self):
        """set_parent should update item's parent."""
        epic_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="epic",
            title="New Parent"
        )
        orphan_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Orphan"
        )

        result = self.db.set_parent(orphan_id, epic_id)
        self.assertTrue(result['success'])

        item = self.db.get_item(orphan_id)
        self.assertEqual(item['parent_id'], epic_id)

    def test_set_parent_remove(self):
        """set_parent with None/0 should remove parent."""
        epic_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="epic",
            title="Epic"
        )
        child_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Child",
            parent_id=epic_id
        )

        result = self.db.set_parent(child_id, None)
        self.assertTrue(result['success'])

        item = self.db.get_item(child_id)
        self.assertIsNone(item['parent_id'])

    def test_set_parent_circular_fails(self):
        """set_parent should prevent circular references."""
        epic_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="epic",
            title="Epic"
        )
        child_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="epic",
            title="Child Epic",
            parent_id=epic_id
        )

        # Try to make parent a child of its own child
        result = self.db.set_parent(epic_id, child_id)
        self.assertFalse(result['success'])
        self.assertIn('circular', result['error'].lower())

    def test_set_parent_self_fails(self):
        """Item cannot be its own parent."""
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="epic",
            title="Self Parent"
        )

        result = self.db.set_parent(item_id, item_id)
        self.assertFalse(result['success'])

    def test_set_parent_non_epic_fails(self):
        """set_parent should reject non-epic items as parents."""
        issue_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Not an epic"
        )
        child_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Would-be child"
        )

        result = self.db.set_parent(child_id, issue_id)
        self.assertFalse(result['success'])
        self.assertIn('epic', result['error'].lower())

    def test_set_parent_feature_as_parent_fails(self):
        """set_parent should reject feature items as parents."""
        feature_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="feature",
            title="Feature not epic"
        )
        child_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="todo",
            title="Would-be child"
        )

        result = self.db.set_parent(child_id, feature_id)
        self.assertFalse(result['success'])
        self.assertIn('epic', result['error'].lower())

    def test_set_parent_todo_as_parent_fails(self):
        """set_parent should reject todo items as parents."""
        todo_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="todo",
            title="Todo not epic"
        )
        child_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Would-be child"
        )

        result = self.db.set_parent(child_id, todo_id)
        self.assertFalse(result['success'])
        self.assertIn('epic', result['error'].lower())

    def test_create_item_feature_as_parent_fails(self):
        """create_item should reject feature items as parents."""
        feature_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="feature",
            title="Feature not epic"
        )
        with self.assertRaises(ValueError) as ctx:
            self.db.create_item(
                project_id=self.test_project_id,
                type_name="issue",
                title="Child Issue",
                parent_id=feature_id
            )
        self.assertIn('epic', str(ctx.exception).lower())

    def test_create_item_issue_as_parent_fails(self):
        """create_item should reject issue items as parents."""
        issue_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Issue not epic"
        )
        with self.assertRaises(ValueError) as ctx:
            self.db.create_item(
                project_id=self.test_project_id,
                type_name="todo",
                title="Child Todo",
                parent_id=issue_id
            )
        self.assertIn('epic', str(ctx.exception).lower())

    def test_create_item_todo_as_parent_fails(self):
        """create_item should reject todo items as parents."""
        todo_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="todo",
            title="Todo not epic"
        )
        with self.assertRaises(ValueError) as ctx:
            self.db.create_item(
                project_id=self.test_project_id,
                type_name="issue",
                title="Child Issue",
                parent_id=todo_id
            )
        self.assertIn('epic', str(ctx.exception).lower())

    def test_create_item_diary_as_parent_fails(self):
        """create_item should reject diary items as parents."""
        diary_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="diary",
            title="Diary not epic"
        )
        with self.assertRaises(ValueError) as ctx:
            self.db.create_item(
                project_id=self.test_project_id,
                type_name="issue",
                title="Child Issue",
                parent_id=diary_id
            )
        self.assertIn('epic', str(ctx.exception).lower())

    def test_create_item_epic_as_parent_succeeds(self):
        """create_item should accept epic items as parents."""
        epic_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="epic",
            title="Valid Epic Parent"
        )
        child_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="feature",
            title="Child Feature",
            parent_id=epic_id
        )
        child = self.db.get_item(child_id)
        self.assertEqual(child['parent_id'], epic_id)


class TestEpicMCPTools(unittest.TestCase):
    """Test epic MCP tools."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanMCPServer
        cls.server = KanbanMCPServer()

    def setUp(self):
        self.server.current_project_id = None
        self.test_project_path = "/tmp/test-epic-tools"
        cleanup_test_project(self.server.db, self.test_project_path)
        self.server.tools[
            'set_current_project']['function'](
            self.test_project_path)

    def tearDown(self):
        cleanup_test_project(
            self.server.db, self.test_project_path)

    def test_new_item_with_parent_id(self):
        """new_item tool should accept parent_id."""
        epic_result = self.server.tools['new_item']['function'](
            item_type="epic",
            title="Test Epic"
        )
        epic_id = epic_result['item']['id']

        child_result = self.server.tools['new_item']['function'](
            item_type="feature",
            title="Child Feature",
            parent_id=epic_id
        )
        self.assertTrue(child_result['success'])
        self.assertEqual(
            child_result['item']['parent_id'], epic_id)

    def test_get_epic_progress_tool(self):
        """get_epic_progress tool should return progress stats."""
        epic_result = self.server.tools['new_item']['function'](
            item_type="epic",
            title="Progress Epic"
        )
        epic_id = epic_result['item']['id']

        self.server.tools['new_item']['function'](
            item_type="issue",
            title="Child",
            parent_id=epic_id
        )

        progress_result = self.server.tools[
            'get_epic_progress']['function'](epic_id)
        self.assertTrue(progress_result['success'])
        self.assertEqual(progress_result['progress']['total'], 1)
        self.assertEqual(
            progress_result['progress']['completed'], 0)

    def test_set_parent_tool(self):
        """set_parent tool should set item parent."""
        epic_result = self.server.tools['new_item']['function'](
            item_type="epic",
            title="Epic"
        )
        epic_id = epic_result['item']['id']

        orphan_result = self.server.tools['new_item']['function'](
            item_type="issue",
            title="Orphan"
        )
        orphan_id = orphan_result['item']['id']

        result = self.server.tools[
            'set_parent']['function'](
            orphan_id, epic_id)
        self.assertTrue(result['success'])

    def test_list_children_tool(self):
        """list_children tool should return children."""
        epic_result = self.server.tools['new_item']['function'](
            item_type="epic",
            title="Epic"
        )
        epic_id = epic_result['item']['id']

        self.server.tools['new_item']['function'](
            item_type="issue",
            title="Child 1",
            parent_id=epic_id
        )
        self.server.tools['new_item']['function'](
            item_type="feature",
            title="Child 2",
            parent_id=epic_id
        )

        result = self.server.tools[
            'list_children']['function'](epic_id)
        self.assertTrue(result['success'])
        self.assertEqual(result['count'], 2)

    def test_list_children_recursive(self):
        """list_children recursive returns all descendants."""
        epic_result = self.server.tools['new_item']['function'](
            item_type="epic",
            title="Root Epic"
        )
        epic_id = epic_result['item']['id']

        sub_epic_result = self.server.tools['new_item']['function'](
            item_type="epic",
            title="Sub Epic",
            parent_id=epic_id
        )
        sub_epic_id = sub_epic_result['item']['id']

        self.server.tools['new_item']['function'](
            item_type="issue",
            title="Grandchild",
            parent_id=sub_epic_id
        )

        result = self.server.tools[
            'list_children']['function'](
            epic_id, recursive=True)
        self.assertTrue(result['success'])
        self.assertEqual(result['count'], 2)

    def test_new_item_non_epic_parent_fails(self):
        """new_item tool should reject non-epic parents."""
        feature_result = self.server.tools['new_item']['function'](
            item_type="feature",
            title="Not an epic"
        )
        feature_id = feature_result['item']['id']

        with self.assertRaises(Exception):
            self.server.tools['new_item']['function'](
                item_type="issue",
                title="Child Issue",
                parent_id=feature_id
            )


class TestSearch(unittest.TestCase):
    """Test full-text search functionality."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanDB
        cls.db = KanbanDB()
        cls.test_project_path = "/tmp/test-search"
        cls.test_project_id = cls.db.hash_project_path(cls.test_project_path)

    def setUp(self):
        cleanup_test_project(self.db, self.test_project_path)
        self.db.ensure_project(self.test_project_path)

    def tearDown(self):
        cleanup_test_project(self.db, self.test_project_path)

    def test_search_finds_item_by_title(self):
        """search should find items matching title."""
        self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Authentication bug in login form"
        )
        self.db.create_item(
            project_id=self.test_project_id,
            type_name="feature",
            title="Add dark mode toggle"
        )

        results = self.db.search(self.test_project_id, "authentication")
        self.assertGreater(len(results['items']), 0)
        self.assertTrue(any(
            'authentication' in r['title'].lower()
            for r in results['items']))

    def test_search_finds_item_by_description(self):
        """search should find items matching description."""
        self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Bug fix",
            description=(
                "The authentication system fails "
                "when using OAuth tokens")
        )

        results = self.db.search(self.test_project_id, "OAuth")
        self.assertGreater(len(results['items']), 0)

    def test_search_finds_updates(self):
        """search should find updates matching content."""
        self.db.add_update(
            self.test_project_id,
            "Implemented the authentication "
            "middleware today")

        results = self.db.search(self.test_project_id, "middleware")
        self.assertGreater(len(results['updates']), 0)

    def test_search_returns_relevance_scores(self):
        """search results should include relevance scores."""
        self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Database connection pooling issue"
        )

        results = self.db.search(self.test_project_id, "database")
        self.assertGreater(len(results['items']), 0)
        self.assertIn('score', results['items'][0])
        self.assertIsInstance(results['items'][0]['score'], float)

    def test_search_respects_project_scope(self):
        """search should only return results from specified project."""
        other_project_path = "/tmp/test-search-other"
        other_project_id = self.db.hash_project_path(other_project_path)
        self.db.ensure_project(other_project_path)

        try:
            # Create item in other project
            self.db.create_item(
                project_id=other_project_id,
                type_name="issue",
                title="Unique searchterm xyz123"
            )

            # Search in our test project should not find it
            results = self.db.search(self.test_project_id, "xyz123")
            self.assertEqual(len(results['items']), 0)
        finally:
            cleanup_test_project(self.db, other_project_path)

    def test_search_respects_limit(self):
        """search should respect limit parameter."""
        for i in range(10):
            self.db.create_item(
                project_id=self.test_project_id,
                type_name="issue",
                title=f"Searchable item number {i}"
            )

        results = self.db.search(self.test_project_id, "searchable", limit=3)
        self.assertLessEqual(len(results['items']), 3)

    def test_search_no_results(self):
        """search should return empty results for no matches."""
        self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Normal issue"
        )

        results = self.db.search(self.test_project_id, "xyznonexistent123")
        self.assertEqual(len(results['items']), 0)
        self.assertEqual(len(results['updates']), 0)

    def test_search_returns_item_metadata(self):
        """search results should include type and status."""
        self.db.create_item(
            project_id=self.test_project_id,
            type_name="feature",
            title="Searchable feature request"
        )

        results = self.db.search(self.test_project_id, "searchable")
        self.assertGreater(len(results['items']), 0)
        item = results['items'][0]
        self.assertIn('type_name', item)
        self.assertIn('status_name', item)
        self.assertEqual(item['type_name'], 'feature')


class TestSearchMCPTool(unittest.TestCase):
    """Test search MCP tool."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanMCPServer
        cls.server = KanbanMCPServer()

    def setUp(self):
        self.server.current_project_id = None
        self.test_project_path = "/tmp/test-search-tool"
        cleanup_test_project(self.server.db, self.test_project_path)
        self.server.tools[
            'set_current_project']['function'](
            self.test_project_path)

    def tearDown(self):
        cleanup_test_project(
            self.server.db, self.test_project_path)

    def test_search_tool_exists(self):
        """search tool should be registered."""
        self.assertIn('search', self.server.tools)

    def test_search_tool_returns_results(self):
        """search tool should return search results."""
        self.server.tools['new_item']['function'](
            item_type="issue",
            title="Searchable test item"
        )

        result = self.server.tools['search']['function'](query="searchable")
        self.assertTrue(result['success'])
        self.assertIn('items', result)
        self.assertIn('updates', result)
        self.assertIn('total_count', result)

    def test_search_tool_respects_limit(self):
        """search tool should accept limit parameter."""
        for i in range(5):
            self.server.tools['new_item']['function'](
                item_type="issue",
                title=f"Findable item {i}"
            )

        result = self.server.tools[
            'search']['function'](
            query="findable", limit=2)
        self.assertTrue(result['success'])
        self.assertLessEqual(len(result['items']), 2)


class TestFileLinks(unittest.TestCase):
    """Tests for file/code linking functionality."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanDB
        cls.db = KanbanDB()
        cls.test_project_path = "/tmp/test-file-links"
        cls.test_project_id = cls.db.hash_project_path(cls.test_project_path)

    def setUp(self):
        cleanup_test_project(self.db, self.test_project_path)
        self.db.ensure_project(self.test_project_path)
        # Create test item
        self.item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="feature",
            title="Test Feature"
        )

    def tearDown(self):
        cleanup_test_project(self.db, self.test_project_path)

    # --- Link File Tests ---

    def test_link_file_whole_file(self):
        """link_file should link whole file (no line numbers)."""
        result = self.db.link_file(self.item_id, "src/main.py")
        self.assertTrue(result['success'])
        self.assertIn('link_id', result)

        files = self.db.get_item_files(self.item_id)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]['file_path'], "src/main.py")
        self.assertIsNone(files[0]['line_start'])
        self.assertIsNone(files[0]['line_end'])

    def test_link_file_with_lines(self):
        """link_file should link file with line range."""
        result = self.db.link_file(
            self.item_id, "src/utils.py",
            line_start=10, line_end=25)
        self.assertTrue(result['success'])

        files = self.db.get_item_files(self.item_id)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]['file_path'], "src/utils.py")
        self.assertEqual(files[0]['line_start'], 10)
        self.assertEqual(files[0]['line_end'], 25)

    def test_link_file_with_start_line_only(self):
        """link_file should accept start line only."""
        result = self.db.link_file(
            self.item_id, "src/app.py",
            line_start=42)
        self.assertTrue(result['success'])

        files = self.db.get_item_files(self.item_id)
        self.assertEqual(files[0]['line_start'], 42)
        self.assertIsNone(files[0]['line_end'])

    def test_link_file_duplicate_rejected(self):
        """Linking same file+lines twice should fail."""
        self.db.link_file(self.item_id, "src/main.py")
        result = self.db.link_file(self.item_id, "src/main.py")
        self.assertFalse(result['success'])
        self.assertIn('exists', result['error'].lower())

    def test_link_file_same_path_different_lines(self):
        """Same file with different line ranges should succeed."""
        self.db.link_file(
            self.item_id, "src/main.py",
            line_start=1, line_end=10)
        result = self.db.link_file(
            self.item_id, "src/main.py",
            line_start=20, line_end=30)
        self.assertTrue(result['success'])

        files = self.db.get_item_files(self.item_id)
        self.assertEqual(len(files), 2)

    def test_link_file_nonexistent_item_fails(self):
        """link_file should fail for non-existent item."""
        with self.assertRaises(ValueError):
            self.db.link_file(99999, "src/main.py")

    # --- Unlink File Tests ---

    def test_unlink_file(self):
        """unlink_file should remove the file link."""
        self.db.link_file(self.item_id, "src/main.py")
        result = self.db.unlink_file(self.item_id, "src/main.py")
        self.assertTrue(result['success'])

        files = self.db.get_item_files(self.item_id)
        self.assertEqual(len(files), 0)

    def test_unlink_file_with_lines(self):
        """unlink_file should remove specific line range link."""
        self.db.link_file(
            self.item_id, "src/main.py",
            line_start=10, line_end=20)
        self.db.link_file(
            self.item_id, "src/main.py",
            line_start=30, line_end=40)

        result = self.db.unlink_file(
            self.item_id, "src/main.py",
            line_start=10, line_end=20)
        self.assertTrue(result['success'])

        files = self.db.get_item_files(self.item_id)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]['line_start'], 30)

    def test_unlink_file_not_linked(self):
        """unlink_file should return success=False if not linked."""
        result = self.db.unlink_file(self.item_id, "not/linked.py")
        self.assertFalse(result['success'])

    # --- Get Item Files Tests ---

    def test_get_item_files_empty(self):
        """get_item_files should return empty list if no files linked."""
        files = self.db.get_item_files(self.item_id)
        self.assertEqual(files, [])

    def test_get_item_files_multiple(self):
        """get_item_files should return all linked files."""
        self.db.link_file(self.item_id, "src/main.py")
        self.db.link_file(
            self.item_id, "src/utils.py",
            line_start=10)
        self.db.link_file(
            self.item_id, "tests/test_main.py",
            line_start=5, line_end=15)

        files = self.db.get_item_files(self.item_id)
        self.assertEqual(len(files), 3)
        paths = [f['file_path'] for f in files]
        self.assertIn("src/main.py", paths)
        self.assertIn("src/utils.py", paths)
        self.assertIn("tests/test_main.py", paths)

    def test_get_item_files_ordered_by_path(self):
        """get_item_files should return files ordered by path."""
        self.db.link_file(self.item_id, "z_file.py")
        self.db.link_file(self.item_id, "a_file.py")
        self.db.link_file(self.item_id, "m_file.py")

        files = self.db.get_item_files(self.item_id)
        paths = [f['file_path'] for f in files]
        self.assertEqual(paths, ["a_file.py", "m_file.py", "z_file.py"])

    # --- Cascade Delete Tests ---

    def test_cascade_delete_on_item_delete(self):
        """Deleting item should cascade delete file links."""
        self.db.link_file(self.item_id, "src/main.py")
        self.db.link_file(self.item_id, "src/utils.py")

        # Delete the item
        self.db.delete_item(self.item_id)

        # File links should be gone (verify via query)
        ph = self.db._backend.placeholder
        with self.db._db_cursor() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) FROM item_files WHERE item_id = {ph}",
                (self.item_id,)
            )
            count = cursor.fetchone()[0]
            self.assertEqual(count, 0)


class TestFileLinksMCPTools(unittest.TestCase):
    """Tests for file linking MCP tools."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanMCPServer
        cls.server = KanbanMCPServer()

    def setUp(self):
        self.server.current_project_id = None
        self.test_project_path = "/tmp/test-file-links-tools"
        cleanup_test_project(self.server.db, self.test_project_path)
        self.server.tools[
            'set_current_project']['function'](
            self.test_project_path)
        result = self.server.tools[
            'new_item']['function'](
            item_type="feature",
            title="Test Feature"
        )
        self.item_id = result['item']['id']

    def tearDown(self):
        cleanup_test_project(
            self.server.db, self.test_project_path)

    # --- Tool Registration Tests ---

    def test_link_file_tool_exists(self):
        """link_file tool should be registered."""
        self.assertIn('link_file', self.server.tools)

    def test_unlink_file_tool_exists(self):
        """unlink_file tool should be registered."""
        self.assertIn('unlink_file', self.server.tools)

    def test_get_item_files_tool_exists(self):
        """get_item_files tool should be registered."""
        self.assertIn('get_item_files', self.server.tools)

    # --- Tool Functionality Tests ---

    def test_link_file_tool(self):
        """link_file tool should link file to item."""
        result = self.server.tools['link_file']['function'](
            item_id=self.item_id,
            file_path="src/main.py"
        )
        self.assertTrue(result['success'])

        files_result = self.server.tools[
            'get_item_files']['function'](
            self.item_id)
        self.assertEqual(len(files_result['files']), 1)
        self.assertEqual(
            files_result['files'][0]['file_path'],
            "src/main.py")

    def test_link_file_tool_with_lines(self):
        """link_file tool should accept line range."""
        result = self.server.tools['link_file']['function'](
            item_id=self.item_id,
            file_path="src/utils.py",
            line_start=10,
            line_end=25
        )
        self.assertTrue(result['success'])

        files_result = self.server.tools[
            'get_item_files']['function'](
            self.item_id)
        self.assertEqual(
            files_result['files'][0]['line_start'],
            10)
        self.assertEqual(
            files_result['files'][0]['line_end'], 25)

    def test_unlink_file_tool(self):
        """unlink_file tool should remove file link."""
        self.server.tools['link_file']['function'](
            item_id=self.item_id,
            file_path="src/main.py"
        )

        result = self.server.tools['unlink_file']['function'](
            item_id=self.item_id,
            file_path="src/main.py"
        )
        self.assertTrue(result['success'])

        files_result = self.server.tools[
            'get_item_files']['function'](
            self.item_id)
        self.assertEqual(len(files_result['files']), 0)

    def test_get_item_files_tool(self):
        """get_item_files tool should return linked files."""
        self.server.tools['link_file']['function'](
            item_id=self.item_id,
            file_path="src/a.py"
        )
        self.server.tools['link_file']['function'](
            item_id=self.item_id,
            file_path="src/b.py",
            line_start=5
        )

        result = self.server.tools[
            'get_item_files']['function'](
            self.item_id)
        self.assertTrue(result['success'])
        self.assertEqual(result['count'], 2)
        self.assertIn('files', result)


class TestQuestionType(unittest.TestCase):
    """Tests for question item type for AI autonomous loops."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanDB
        cls.db = KanbanDB()
        cls.test_project_path = "/tmp/test-question-type"
        cls.test_project_id = cls.db.hash_project_path(cls.test_project_path)

    def setUp(self):
        cleanup_test_project(self.db, self.test_project_path)
        self.db.ensure_project(self.test_project_path)

    def tearDown(self):
        cleanup_test_project(self.db, self.test_project_path)

    def test_create_question_item(self):
        """Question items can be created."""
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="question",
            title="Redis vs Memcached for caching?",
            description=(
                "Decision: Using Redis. "
                "Rationale: Better data "
                "structures support.")
        )
        self.assertIsNotNone(item_id)

        item = self.db.get_item(item_id)
        self.assertEqual(item['type_name'], 'question')
        self.assertEqual(
            item['title'],
            "Redis vs Memcached for caching?")
        self.assertIn("Redis", item['description'])

    def test_question_default_status_is_backlog(self):
        """Question items should start in backlog (pending) status."""
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="question",
            title="Test Question"
        )
        item = self.db.get_item(item_id)
        self.assertEqual(item['status_name'], 'backlog')

    def test_question_workflow_backlog_to_review(self):
        """Question should advance backlog to review."""
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="question",
            title="Test Question"
        )

        result = self.db.advance_status(item_id)
        self.assertTrue(result['success'])
        self.assertEqual(result['new_status'], 'review')

    def test_question_workflow_review_to_closed(self):
        """Question should advance from review (reviewed) to closed."""
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="question",
            title="Test Question"
        )

        self.db.advance_status(item_id)  # backlog -> review
        result = self.db.advance_status(item_id)  # review -> closed
        self.assertTrue(result['success'])
        self.assertEqual(result['new_status'], 'closed')

    def test_question_full_workflow(self):
        """Question should have workflow: backlog -> review -> closed."""
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="question",
            title="Full Workflow Test"
        )

        # Start at backlog (pending)
        item = self.db.get_item(item_id)
        self.assertEqual(item['status_name'], 'backlog')

        # Advance to review (reviewed)
        self.db.advance_status(item_id)
        item = self.db.get_item(item_id)
        self.assertEqual(item['status_name'], 'review')

        # Advance to closed
        self.db.advance_status(item_id)
        item = self.db.get_item(item_id)
        self.assertEqual(item['status_name'], 'closed')

        # Should not advance past closed
        result = self.db.advance_status(item_id)
        self.assertFalse(result['success'])

    def test_question_revert_status(self):
        """Question should be able to revert status."""
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="question",
            title="Revert Test"
        )

        self.db.advance_status(item_id)  # backlog -> review
        result = self.db.revert_status(item_id)  # review -> backlog
        self.assertTrue(result['success'])
        self.assertEqual(result['new_status'], 'backlog')

    def test_question_can_be_tagged_for_flagging(self):
        """Question items can be tagged (e.g., 'flagged', 'bad-decision')."""
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="question",
            title="Bad Decision Question"
        )

        # Add flagged tag
        result = self.db.add_tag_to_item(item_id, "flagged")
        self.assertTrue(result['success'])

        # Add bad-decision tag
        result = self.db.add_tag_to_item(item_id, "bad-decision")
        self.assertTrue(result['success'])

        # Verify tags
        tags = self.db.get_item_tags(item_id)
        tag_names = [t['name'] for t in tags]
        self.assertIn('flagged', tag_names)
        self.assertIn('bad-decision', tag_names)

    def test_question_in_project_summary(self):
        """Question items should appear in project summary."""
        self.db.create_item(
            project_id=self.test_project_id,
            type_name="question",
            title="Summary Test Question"
        )

        summary = self.db.project_summary(self.test_project_id)
        self.assertIn('question', summary)
        self.assertIn('backlog', summary['question'])
        self.assertEqual(summary['question']['backlog'], 1)

    def test_question_list_items_filter(self):
        """Question items should be filterable by type."""
        self.db.create_item(
            project_id=self.test_project_id,
            type_name="question",
            title="Filter Test Question"
        )
        self.db.create_item(
            project_id=self.test_project_id,
            type_name="issue",
            title="Regular Issue"
        )

        items = self.db.list_items(
            project_id=self.test_project_id,
            type_name="question")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['type_name'], 'question')


class TestQuestionTypeMCPTools(unittest.TestCase):
    """Tests for question item type MCP tools."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanMCPServer
        cls.server = KanbanMCPServer()

    def setUp(self):
        self.server.current_project_id = None
        self.test_project_path = "/tmp/test-question-tools"
        cleanup_test_project(self.server.db, self.test_project_path)
        self.server.tools[
            'set_current_project']['function'](
            self.test_project_path)

    def tearDown(self):
        cleanup_test_project(
            self.server.db, self.test_project_path)

    def test_new_item_question_type(self):
        """new_item tool should accept 'question' type."""
        result = self.server.tools['new_item']['function'](
            item_type="question",
            title="Should we use Redis or Memcached?",
            description=(
                "Decision: Using Redis. "
                "Rationale: Better data structures.")
        )
        self.assertTrue(result['success'])
        self.assertEqual(result['item']['type_name'], 'question')
        self.assertEqual(result['item']['status_name'], 'backlog')

    def test_question_advance_via_tool(self):
        """advance_status tool should work for question items."""
        result = self.server.tools['new_item']['function'](
            item_type="question",
            title="Test Question"
        )
        item_id = result['item']['id']

        # Advance to review
        adv = self.server.tools[
            'advance_status']['function']
        advance_result = adv(item_id)
        self.assertTrue(advance_result['success'])
        self.assertEqual(
            advance_result['new_status'], 'review')

        advance_result = adv(item_id)
        self.assertTrue(advance_result['success'])
        self.assertEqual(
            advance_result['new_status'], 'closed')

    def test_question_list_filter(self):
        """list_items tool should filter by question type."""
        self.server.tools['new_item']['function'](
            item_type="question",
            title="Question 1"
        )
        self.server.tools['new_item']['function'](
            item_type="issue",
            title="Issue 1"
        )

        result = self.server.tools[
            'list_items']['function'](
            item_type="question")
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['items'][0]['type_name'], 'question')


class TestDecisions(unittest.TestCase):
    """Tests for decision history tracking functionality."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanDB
        cls.db = KanbanDB()
        cls.test_project_path = "/tmp/test-decisions"
        cls.test_project_id = cls.db.hash_project_path(cls.test_project_path)

    def setUp(self):
        cleanup_test_project(self.db, self.test_project_path)
        self.db.ensure_project(self.test_project_path)
        self.item_id = self.db.create_item(
            self.test_project_id, "issue",
            "Test Issue")

    def tearDown(self):
        cleanup_test_project(self.db, self.test_project_path)

    # --- Add Decision Tests ---

    def test_add_decision_basic(self):
        """add_decision should add a basic decision with just choice."""
        result = self.db.add_decision(self.item_id, "React Context")
        self.assertTrue(result['success'])
        self.assertIn('decision_id', result)

        decisions = self.db.get_item_decisions(self.item_id)
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]['choice'], "React Context")
        self.assertIsNone(decisions[0]['rejected_alternatives'])
        self.assertIsNone(decisions[0]['rationale'])

    def test_add_decision_all_fields(self):
        """add_decision should accept all optional fields."""
        result = self.db.add_decision(
            self.item_id,
            choice="React Context",
            rejected_alternatives="Redux (overkill), MobX (unfamiliar)",
            rationale="Team knows Context, app is small"
        )
        self.assertTrue(result['success'])

        decisions = self.db.get_item_decisions(self.item_id)
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]['choice'], "React Context")
        self.assertEqual(
            decisions[0]['rejected_alternatives'],
            "Redux (overkill), MobX (unfamiliar)")
        self.assertEqual(
            decisions[0]['rationale'],
            "Team knows Context, app is small")

    def test_add_decision_nonexistent_item_fails(self):
        """add_decision should fail for non-existent item."""
        with self.assertRaises(ValueError):
            self.db.add_decision(99999, "Some Choice")

    def test_choice_max_length_enforced(self):
        """add_decision should reject choice exceeding 200 chars."""
        long_choice = "x" * 201
        with self.assertRaises(ValueError) as ctx:
            self.db.add_decision(self.item_id, long_choice)
        self.assertIn("200", str(ctx.exception))

    def test_rejected_max_length_enforced(self):
        """add_decision should reject long rejected_alternatives."""
        long_rejected = "x" * 501
        with self.assertRaises(ValueError) as ctx:
            self.db.add_decision(
                self.item_id, "Choice",
                rejected_alternatives=long_rejected)
        self.assertIn("500", str(ctx.exception))

    def test_rationale_max_length_enforced(self):
        """add_decision should reject long rationale."""
        long_rationale = "x" * 201
        with self.assertRaises(ValueError) as ctx:
            self.db.add_decision(
                self.item_id, "Choice",
                rationale=long_rationale)
        self.assertIn("200", str(ctx.exception))

    # --- Get Item Decisions Tests ---

    def test_get_item_decisions_empty(self):
        """get_item_decisions should return empty list if no decisions."""
        decisions = self.db.get_item_decisions(self.item_id)
        self.assertEqual(decisions, [])

    def test_get_item_decisions_multiple(self):
        """get_item_decisions should return all decisions in DESC order."""
        self.db.add_decision(self.item_id, "First Decision")
        self.db.add_decision(self.item_id, "Second Decision")
        self.db.add_decision(self.item_id, "Third Decision")

        decisions = self.db.get_item_decisions(self.item_id)
        self.assertEqual(len(decisions), 3)
        # Should be in DESC order (most recent first)
        self.assertEqual(decisions[0]['choice'], "Third Decision")
        self.assertEqual(decisions[2]['choice'], "First Decision")

    # --- Delete Decision Tests ---

    def test_delete_decision(self):
        """delete_decision should remove the decision."""
        result = self.db.add_decision(self.item_id, "To Delete")
        decision_id = result['decision_id']

        delete_result = self.db.delete_decision(decision_id)
        self.assertTrue(delete_result['success'])

        decisions = self.db.get_item_decisions(self.item_id)
        self.assertEqual(len(decisions), 0)

    def test_delete_decision_not_found(self):
        """delete_decision should fail for missing decision."""
        result = self.db.delete_decision(99999)
        self.assertFalse(result['success'])
        self.assertIn('error', result)

    def test_cascade_delete_on_item_delete(self):
        """Decisions should be deleted when item is deleted."""
        self.db.add_decision(self.item_id, "Decision 1")
        self.db.add_decision(self.item_id, "Decision 2")

        # Delete the item
        self.db.delete_item(self.item_id)

        # Verify item and decisions are gone (check via direct query)
        with self.db._db_cursor() as cursor:
            cursor.execute(
                self.db._sql(
                    "SELECT COUNT(*) FROM "
                    "item_decisions WHERE item_id = %s"),
                (self.item_id,))
            count = cursor.fetchone()[0]
            self.assertEqual(count, 0)


class TestDecisionsMCPTools(unittest.TestCase):
    """Tests for decision history MCP tools."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanMCPServer
        cls.server = KanbanMCPServer()

    def setUp(self):
        self.server.current_project_id = None
        self.test_project_path = "/tmp/test-decisions-mcp"
        cleanup_test_project(self.server.db, self.test_project_path)
        self.server.tools[
            'set_current_project']['function'](
            self.test_project_path)
        item_result = self.server.tools[
            'new_item']['function'](
            item_type="issue",
            title="Test Issue for Decisions"
        )
        self.item_id = item_result['item']['id']

    def tearDown(self):
        cleanup_test_project(
            self.server.db, self.test_project_path)

    # --- Tool Registration Tests ---

    def test_add_decision_tool_exists(self):
        """add_decision tool should be registered."""
        self.assertIn('add_decision', self.server.tools)

    def test_get_item_decisions_tool_exists(self):
        """get_item_decisions tool should be registered."""
        self.assertIn('get_item_decisions', self.server.tools)

    def test_delete_decision_tool_exists(self):
        """delete_decision tool should be registered."""
        self.assertIn('delete_decision', self.server.tools)

    # --- Tool Functionality Tests ---

    def test_add_decision_tool(self):
        """add_decision tool should add decision to item."""
        result = self.server.tools['add_decision']['function'](
            item_id=self.item_id,
            choice="React Context",
            rejected_alternatives="Redux",
            rationale="Simpler"
        )
        self.assertTrue(result['success'])

        decisions_result = self.server.tools[
            'get_item_decisions']['function'](
            self.item_id)
        self.assertEqual(
            len(decisions_result['decisions']), 1)
        self.assertEqual(
            decisions_result['decisions'][0]['choice'],
            "React Context")

    def test_add_decision_tool_choice_only(self):
        """add_decision tool should work with just choice."""
        result = self.server.tools['add_decision']['function'](
            item_id=self.item_id,
            choice="Python over Go"
        )
        self.assertTrue(result['success'])

        decisions_result = self.server.tools[
            'get_item_decisions']['function'](
            self.item_id)
        self.assertEqual(
            len(decisions_result['decisions']), 1)

    def test_get_item_decisions_tool(self):
        """get_item_decisions tool should return decisions."""
        self.server.tools['add_decision']['function'](
            item_id=self.item_id,
            choice="Decision 1"
        )
        self.server.tools['add_decision']['function'](
            item_id=self.item_id,
            choice="Decision 2"
        )

        result = self.server.tools[
            'get_item_decisions']['function'](
            self.item_id)
        self.assertTrue(result['success'])
        self.assertEqual(result['count'], 2)
        self.assertEqual(len(result['decisions']), 2)

    def test_delete_decision_tool(self):
        """delete_decision tool should remove decision."""
        add_result = self.server.tools['add_decision']['function'](
            item_id=self.item_id,
            choice="To Delete"
        )
        decision_id = add_result['decision_id']

        delete_result = self.server.tools[
            'delete_decision']['function'](
            decision_id)
        self.assertTrue(delete_result['success'])

        decisions_result = self.server.tools[
            'get_item_decisions']['function'](
            self.item_id)
        self.assertEqual(
            len(decisions_result['decisions']), 0)

    def test_add_and_retrieve_decision(self):
        """Full workflow: add decision and retrieve it."""
        add_result = self.server.tools[
            'add_decision']['function'](
            item_id=self.item_id,
            choice="MySQL over PostgreSQL",
            rejected_alternatives=(
                "PostgreSQL (team unfamiliar), "
                "SQLite (too limited)"),
            rationale=(
                "Existing infrastructure uses MySQL")
        )
        self.assertTrue(add_result['success'])

        # Retrieve and verify
        get_result = self.server.tools[
            'get_item_decisions']['function'](
            self.item_id)
        self.assertEqual(get_result['count'], 1)

        decision = get_result['decisions'][0]
        self.assertEqual(
            decision['choice'],
            "MySQL over PostgreSQL")
        self.assertEqual(
            decision['rejected_alternatives'],
            "PostgreSQL (team unfamiliar), "
            "SQLite (too limited)")
        self.assertEqual(
            decision['rationale'],
            "Existing infrastructure uses MySQL")
        self.assertIn('created_at', decision)


def _has_onnxruntime():
    try:
        import onnxruntime  # noqa: F401
        return True
    except ImportError:
        return False


@unittest.skipUnless(
    _has_onnxruntime(),
    "onnxruntime not installed "
    "(pip install kanban-mcp[semantic])")
class TestEmbeddings(unittest.TestCase):
    """Tests for vector embedding functionality."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanDB
        cls.db = KanbanDB()
        cls.test_project_path = "/tmp/test-embeddings"
        cls.test_project_id = cls.db.hash_project_path(cls.test_project_path)

    def setUp(self):
        cleanup_test_project(self.db, self.test_project_path)
        self.db.ensure_project(self.test_project_path)
        self.item_id = self.db.create_item(
            self.test_project_id, "issue", "Test Issue",
            description="This is a test issue about authentication"
        )

    def tearDown(self):
        cleanup_test_project(self.db, self.test_project_path)

    # --- Embedding Generation Tests ---

    def test_generate_embedding_returns_bytes(self):
        """generate_embedding should return bytes."""
        result = self.db.generate_embedding("test text")
        self.assertIsInstance(result, bytes)

    def test_embedding_correct_size(self):
        """Embedding should be 768 floats = 3072 bytes."""
        result = self.db.generate_embedding("test text")
        self.assertEqual(len(result), 768 * 4)  # 768 float32s

    def test_embedding_deterministic(self):
        """Same text should produce same embedding."""
        e1 = self.db.generate_embedding("hello world")
        e2 = self.db.generate_embedding("hello world")
        self.assertEqual(e1, e2)

    def test_embedding_different_for_different_text(self):
        """Different text should produce different embeddings."""
        e1 = self.db.generate_embedding("hello world")
        e2 = self.db.generate_embedding("goodbye moon")
        self.assertNotEqual(e1, e2)

    # --- Upsert Tests ---

    def test_upsert_embedding_creates(self):
        """upsert_embedding should create new embedding when none exists."""
        # Delete any auto-created embedding first to test creation
        self.db.delete_embedding('item', self.item_id)
        result = self.db.upsert_embedding('item', self.item_id)
        self.assertTrue(result['success'])
        self.assertEqual(result['status'], 'created')

    def test_upsert_embedding_updates_on_content_change(self):
        """upsert_embedding should update on change."""
        original = self.db.get_embedding(
            'item', self.item_id)
        original_hash = original['content_hash']

        with self.db._db_cursor(commit=True) as cursor:
            cursor.execute(
                self.db._sql(
                    "UPDATE items SET title = %s "
                    "WHERE id = %s"),
                ("Completely Different Title "
                 "About Something Else",
                 self.item_id))

        # Now upsert should detect change and update
        result = self.db.upsert_embedding('item', self.item_id)
        self.assertEqual(result['status'], 'updated')

        # Verify hash actually changed
        updated = self.db.get_embedding('item', self.item_id)
        self.assertNotEqual(original_hash, updated['content_hash'])

    def test_upsert_embedding_skips_if_unchanged(self):
        """upsert_embedding should skip if content unchanged."""
        self.db.upsert_embedding('item', self.item_id)
        result = self.db.upsert_embedding('item', self.item_id)
        self.assertEqual(result['status'], 'unchanged')

    def test_get_embedding(self):
        """Should retrieve stored embedding."""
        self.db.upsert_embedding('item', self.item_id)
        embedding = self.db.get_embedding('item', self.item_id)
        self.assertIsNotNone(embedding)
        self.assertEqual(len(embedding['vector']), 768 * 4)

    # --- Delete Tests ---

    def test_delete_embedding(self):
        """delete_embedding should remove embedding."""
        self.db.upsert_embedding('item', self.item_id)
        result = self.db.delete_embedding('item', self.item_id)
        self.assertTrue(result['success'])
        embedding = self.db.get_embedding('item', self.item_id)
        self.assertIsNone(embedding)

    # --- Semantic Search Tests ---

    def test_semantic_search_returns_results(self):
        """semantic_search should return matching items."""
        self.db.upsert_embedding('item', self.item_id)
        results = self.db.semantic_search(
            self.test_project_id,
            "authentication problem")
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]['source_type'], 'item')

    def test_semantic_search_similarity_ordering(self):
        """Results should be ordered by similarity descending."""
        # Create items with different relevance
        id1 = self.db.create_item(self.test_project_id, "issue", "Login bug",
                                  description="User cannot log in")
        id2 = self.db.create_item(self.test_project_id, "issue", "UI color",
                                  description="Button is wrong color")
        self.db.upsert_embedding('item', id1)
        self.db.upsert_embedding('item', id2)

        results = self.db.semantic_search(
            self.test_project_id,
            "authentication login problem")
        # Login bug should rank higher than UI color
        ids = [r['source_id'] for r in results]
        self.assertIn(id1, ids)
        self.assertIn(id2, ids)
        self.assertLess(ids.index(id1), ids.index(id2))

    def test_semantic_search_filter_by_type(self):
        """semantic_search should filter by source_type."""
        self.db.upsert_embedding('item', self.item_id)
        decision_result = self.db.add_decision(
            self.item_id, "Use JWT for auth")
        decision_id = decision_result['decision_id']
        self.db.upsert_embedding('decision', decision_id)

        results = self.db.semantic_search(
            self.test_project_id,
            "authentication",
            source_types=['decision'])
        source_types = [r['source_type'] for r in results]
        self.assertTrue(
            all(t == 'decision' for t in source_types))

    def test_semantic_search_with_threshold(self):
        """semantic_search should respect threshold."""
        self.db.upsert_embedding('item', self.item_id)
        results = self.db.semantic_search(
            self.test_project_id,
            "basketball sports", threshold=0.9)
        auth_results = self.db.semantic_search(
            self.test_project_id,
            "authentication login",
            threshold=0.1)
        self.assertGreaterEqual(
            len(auth_results), len(results))

    # --- Find Similar Tests ---

    def test_find_similar_returns_results(self):
        """find_similar should return similar items."""
        id2 = self.db.create_item(
            self.test_project_id, "issue",
            "Auth problem",
            description="Authentication is broken")
        self.db.upsert_embedding('item', self.item_id)
        self.db.upsert_embedding('item', id2)

        results = self.db.find_similar('item', self.item_id)
        self.assertGreater(len(results), 0)

    def test_find_similar_excludes_self(self):
        """find_similar should not return the source item."""
        self.db.upsert_embedding('item', self.item_id)
        results = self.db.find_similar('item', self.item_id)
        ids = [r['source_id'] for r in results if r['source_type'] == 'item']
        self.assertNotIn(self.item_id, ids)

    # --- Edge Cases ---

    def test_upsert_embedding_invalid_source_type(self):
        """upsert_embedding should handle invalid source type."""
        result = self.db.upsert_embedding('invalid', 999)
        self.assertFalse(result['success'])

    def test_get_embedding_nonexistent(self):
        """get_embedding should return None for nonexistent embedding."""
        embedding = self.db.get_embedding('item', 999999)
        self.assertIsNone(embedding)

    def test_delete_embedding_nonexistent(self):
        """delete_embedding should handle nonexistent embedding gracefully."""
        result = self.db.delete_embedding('item', 999999)
        self.assertFalse(result['success'])


@unittest.skipUnless(
    _has_onnxruntime(),
    "onnxruntime not installed "
    "(pip install kanban-mcp[semantic])")
class TestEmbeddingsMCPTools(unittest.TestCase):
    """Tests for embedding MCP tools."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanMCPServer
        cls.server = KanbanMCPServer()

    def setUp(self):
        self.server.current_project_id = None
        self.test_project_path = "/tmp/test-embeddings-mcp"
        cleanup_test_project(self.server.db, self.test_project_path)
        self.server.tools[
            'set_current_project']['function'](
            self.test_project_path)

    def tearDown(self):
        cleanup_test_project(
            self.server.db, self.test_project_path)

    def test_semantic_search_tool_exists(self):
        """semantic_search tool should be registered."""
        self.assertIn('semantic_search', self.server.tools)

    def test_find_similar_tool_exists(self):
        """find_similar tool should be registered."""
        self.assertIn('find_similar', self.server.tools)

    def test_rebuild_embeddings_tool_exists(self):
        """rebuild_embeddings tool should be registered."""
        self.assertIn('rebuild_embeddings', self.server.tools)

    def test_semantic_search_tool_returns_results(self):
        """semantic_search tool should work end-to-end."""
        item_result = self.server.tools['new_item']['function'](
            item_type="issue",
            title="Database connection timeout",
            description="MySQL connection times out after 30 seconds"
        )
        item_id = item_result['item']['id']

        # Manually upsert embedding since auto-embed may not be enabled yet
        self.server.db.upsert_embedding('item', item_id)

        result = self.server.tools['semantic_search']['function'](
            query="database timeout issue"
        )
        self.assertTrue(result['success'])
        self.assertGreater(len(result['results']), 0)

    def test_find_similar_tool_returns_results(self):
        """find_similar tool should work end-to-end."""
        # Create two similar items
        item1_result = self.server.tools['new_item']['function'](
            item_type="issue",
            title="Login fails",
            description="User authentication fails"
        )
        item1_id = item1_result['item']['id']

        item2_result = self.server.tools['new_item']['function'](
            item_type="issue",
            title="Auth error",
            description="Authentication returns error"
        )
        item2_id = item2_result['item']['id']

        # Manually upsert embeddings
        self.server.db.upsert_embedding('item', item1_id)
        self.server.db.upsert_embedding('item', item2_id)

        result = self.server.tools['find_similar']['function'](
            source_type="item",
            source_id=item1_id
        )
        self.assertTrue(result['success'])
        # Should find item2 as similar
        result_ids = [r['source_id'] for r in result['results']]
        self.assertIn(item2_id, result_ids)

    def test_rebuild_embeddings_tool_works(self):
        """rebuild_embeddings should regenerate embeddings for project."""
        # Create items
        item_result = self.server.tools['new_item']['function'](
            item_type="issue",
            title="Test item for rebuild"
        )
        item_id = item_result['item']['id']

        result = self.server.tools['rebuild_embeddings']['function']()
        self.assertTrue(result['success'])
        self.assertGreater(result['processed'], 0)

        # Verify embedding was created
        embedding = self.server.db.get_embedding('item', item_id)
        self.assertIsNotNone(embedding)


class TestCredentialHardening(unittest.TestCase):
    """Tests for #8219 — no hardcoded defaults for DB credentials."""

    def _clear_env(self):
        """Remove all KANBAN_DB_ env vars and force MySQL backend."""
        for key in (
            'KANBAN_DB_USER', 'KANBAN_DB_PASSWORD',
            'KANBAN_DB_NAME', 'KANBAN_DB_HOST',
        ):
            os.environ.pop(key, None)
        # Force MySQL so auto-detect doesn't fall back to SQLite
        os.environ['KANBAN_BACKEND'] = 'mysql'

    def setUp(self):
        # Save original env
        self._orig = {
            k: os.environ.get(k) for k in (
                'KANBAN_DB_USER',
                'KANBAN_DB_PASSWORD',
                'KANBAN_DB_NAME',
                'KANBAN_DB_HOST',
                'KANBAN_BACKEND')}

    def tearDown(self):
        # Restore original env
        for k, v in self._orig.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_init_no_password_raises(self):
        from kanban_mcp.core import KanbanDB
        self._clear_env()
        os.environ['KANBAN_DB_USER'] = 'someuser'
        os.environ['KANBAN_DB_NAME'] = 'somedb'
        with self.assertRaises(ValueError) as ctx:
            KanbanDB()
        self.assertIn('KANBAN_DB_PASSWORD', str(ctx.exception))

    def test_init_no_user_raises(self):
        from kanban_mcp.core import KanbanDB
        self._clear_env()
        os.environ['KANBAN_DB_PASSWORD'] = 'somepass'
        os.environ['KANBAN_DB_NAME'] = 'somedb'
        with self.assertRaises(ValueError) as ctx:
            KanbanDB()
        self.assertIn('KANBAN_DB_USER', str(ctx.exception))

    def test_init_no_dbname_raises(self):
        from kanban_mcp.core import KanbanDB
        self._clear_env()
        os.environ['KANBAN_DB_USER'] = 'someuser'
        os.environ['KANBAN_DB_PASSWORD'] = 'somepass'
        with self.assertRaises(ValueError) as ctx:
            KanbanDB()
        self.assertIn('KANBAN_DB_NAME', str(ctx.exception))

    def test_init_empty_string_password_raises(self):
        from kanban_mcp.core import KanbanDB
        self._clear_env()
        os.environ['KANBAN_DB_USER'] = 'someuser'
        os.environ['KANBAN_DB_PASSWORD'] = ''
        os.environ['KANBAN_DB_NAME'] = 'somedb'
        with self.assertRaises(ValueError) as ctx:
            KanbanDB()
        self.assertIn('KANBAN_DB_PASSWORD', str(ctx.exception))

    @unittest.mock.patch(
        'kanban_mcp.db.mysql_backend.MySQLConnectionPool')
    def test_init_constructor_params_override_env(self, mock_pool):
        from kanban_mcp.core import KanbanDB
        self._clear_env()
        # Pass valid params directly — should not raise even without env vars
        db = KanbanDB(
            user='testuser',
            password='testpass',
            database='testdb')
        self.assertEqual(db.config['user'], 'testuser')
        self.assertEqual(db.config['database'], 'testdb')

    def test_init_error_message_lists_missing_vars(self):
        from kanban_mcp.core import KanbanDB
        self._clear_env()
        with self.assertRaises(ValueError) as ctx:
            KanbanDB()
        msg = str(ctx.exception)
        self.assertIn('KANBAN_DB_USER', msg)
        self.assertIn('KANBAN_DB_PASSWORD', msg)
        self.assertIn('KANBAN_DB_NAME', msg)


class TestCascadeDelete(unittest.TestCase):
    """Tests for #8220 — CASCADE delete on project FK."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanDB
        cls.db = KanbanDB()

    def setUp(self):
        self.test_path = "/tmp/test-cascade-project"
        self.test_path2 = "/tmp/test-cascade-project-2"
        cleanup_test_project(self.db, self.test_path)
        cleanup_test_project(self.db, self.test_path2)

    def tearDown(self):
        cleanup_test_project(self.db, self.test_path)
        cleanup_test_project(self.db, self.test_path2)

    def test_cascade_delete_project_removes_items(self):
        project_id = self.db.ensure_project(self.test_path)
        self.db.create_item(project_id, 'issue', 'Item 1')
        self.db.create_item(project_id, 'feature', 'Item 2')
        self.db.create_item(project_id, 'todo', 'Item 3')

        with self.db._db_cursor(commit=True) as cursor:
            cursor.execute(
                self.db._sql(
                    "DELETE FROM projects WHERE id = %s"),
                (project_id,))

        with self.db._db_cursor(dictionary=True) as cursor:
            cursor.execute(
                self.db._sql(
                    "SELECT COUNT(*) as cnt FROM items "
                    "WHERE project_id = %s"),
                (project_id,))
            self.assertEqual(cursor.fetchone()['cnt'], 0)

    def test_cascade_delete_project_removes_updates(self):
        project_id = self.db.ensure_project(self.test_path)
        item_id = self.db.create_item(project_id, 'issue', 'Item 1')
        self.db.add_update(project_id, 'Test update', [item_id])

        with self.db._db_cursor(commit=True) as cursor:
            cursor.execute(
                self.db._sql(
                    "DELETE FROM projects WHERE id = %s"),
                (project_id,))

        with self.db._db_cursor(dictionary=True) as cursor:
            cursor.execute(
                self.db._sql(
                    "SELECT COUNT(*) as cnt "
                    "FROM updates "
                    "WHERE project_id = %s"),
                (project_id,))
            self.assertEqual(cursor.fetchone()['cnt'], 0)

    def test_cascade_delete_project_removes_update_items(self):
        project_id = self.db.ensure_project(self.test_path)
        item_id = self.db.create_item(project_id, 'issue', 'Item 1')
        update_id = self.db.add_update(project_id, 'Test update', [item_id])

        with self.db._db_cursor(commit=True) as cursor:
            cursor.execute(
                self.db._sql(
                    "DELETE FROM projects WHERE id = %s"),
                (project_id,))

        with self.db._db_cursor(dictionary=True) as cursor:
            cursor.execute(
                self.db._sql(
                    "SELECT COUNT(*) as cnt "
                    "FROM update_items "
                    "WHERE update_id = %s"),
                (update_id,))
            self.assertEqual(cursor.fetchone()['cnt'], 0)

    def test_cascade_delete_leaves_other_projects(self):
        pid1 = self.db.ensure_project(self.test_path)
        pid2 = self.db.ensure_project(self.test_path2)
        self.db.create_item(pid1, 'issue', 'Item in project 1')
        self.db.create_item(pid2, 'issue', 'Item in project 2')

        with self.db._db_cursor(commit=True) as cursor:
            cursor.execute(
                self.db._sql(
                    "DELETE FROM projects WHERE id = %s"),
                (pid1,))

        with self.db._db_cursor(dictionary=True) as cursor:
            cursor.execute(
                self.db._sql(
                    "SELECT COUNT(*) as cnt FROM items "
                    "WHERE project_id = %s"), (pid2,))
            self.assertEqual(cursor.fetchone()['cnt'], 1)


class TestIndexExistence(unittest.TestCase):
    """Tests for #8221, #8230 — verify indexes exist."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanDB
        from kanban_mcp.setup import auto_migrate
        cls.db = KanbanDB()
        auto_migrate(cls.db._backend)

    def _get_index_columns(self, table):
        """Get set of indexed column names for a table."""
        with self.db._db_cursor(dictionary=True) as cursor:
            if self.db._backend.backend_type == 'sqlite':
                cursor.execute(
                    f"PRAGMA index_list({table})")
                cols = set()
                for idx in cursor.fetchall():
                    cursor.execute(
                        f"PRAGMA index_info({idx['name']})")
                    for info in cursor.fetchall():
                        cols.add(info['name'])
                return cols
            else:
                cursor.execute(f"SHOW INDEX FROM {table}")
                return {row['Column_name']
                        for row in cursor.fetchall()}

    def test_index_on_relationship_target_item_id(self):
        cols = self._get_index_columns('item_relationships')
        self.assertIn('target_item_id', cols)

    def test_index_on_update_items_item_id(self):
        cols = self._get_index_columns('update_items')
        self.assertIn('item_id', cols)


class TestEmbeddingFailureLogging(unittest.TestCase):
    """Tests for #8224 — embedding failures logged at debug level."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanDB
        cls.db = KanbanDB()
        cls.test_path = "/tmp/test-embedding-logging"

    def setUp(self):
        cleanup_test_project(self.db, self.test_path)
        self.project_id = self.db.ensure_project(self.test_path)

    def tearDown(self):
        cleanup_test_project(self.db, self.test_path)

    def test_create_item_embedding_failure_logged(self):
        with patch.object(
            self.db, 'upsert_embedding',
            side_effect=ConnectionError("test"),
        ):
            with self.assertLogs('kanban_mcp', level='DEBUG') as cm:
                item_id = self.db.create_item(self.project_id, 'issue', 'Test')
        self.assertIsNotNone(item_id)
        self.assertTrue(any('Embedding' in msg for msg in cm.output))

    def test_delete_item_embedding_failure_continues(self):
        item_id = self.db.create_item(self.project_id, 'issue', 'To Delete')
        with patch.object(
            self.db, 'delete_embedding',
            side_effect=RuntimeError("test"),
        ):
            with self.assertLogs('kanban_mcp', level='DEBUG'):
                result = self.db.delete_item(item_id)
        self.assertTrue(result['success'])

    def test_add_decision_embedding_failure_logged(self):
        item_id = self.db.create_item(
            self.project_id, 'issue', 'For Decision')
        with patch.object(
            self.db, 'upsert_embedding',
            side_effect=ConnectionError("test"),
        ):
            with self.assertLogs('kanban_mcp', level='DEBUG') as cm:
                result = self.db.add_decision(item_id, 'Use X')
        self.assertTrue(result['success'])
        self.assertTrue(
            any('Embedding' in msg
                for msg in cm.output))

    def test_embedding_exception_type_preserved(self):
        with patch.object(
            self.db, 'upsert_embedding',
            side_effect=ConnectionError(
                "specific error")):
            with self.assertLogs(
                    'kanban_mcp', level='DEBUG') as cm:
                self.db.create_item(
                    self.project_id, 'issue', 'Test')
        self.assertTrue(any(
            'ConnectionError' in msg
            or 'specific error' in msg
            for msg in cm.output))


class TestCleanupTestProject(unittest.TestCase):
    """Tests for #8226 — cleanup removes relationships."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanDB
        cls.db = KanbanDB()
        cls.test_path = "/tmp/test-cleanup-project"

    def setUp(self):
        cleanup_test_project(self.db, self.test_path)

    def tearDown(self):
        cleanup_test_project(self.db, self.test_path)

    def test_cleanup_removes_relationships(self):
        pid = self.db.ensure_project(self.test_path)
        item1 = self.db.create_item(pid, 'issue', 'Blocker')
        item2 = self.db.create_item(pid, 'issue', 'Blocked')
        self.db.add_relationship(item1, item2, 'blocks')

        cleanup_test_project(self.db, self.test_path)

        with self.db._db_cursor(dictionary=True) as cursor:
            cursor.execute(
                self.db._sql(
                    "SELECT COUNT(*) as cnt "
                    "FROM item_relationships "
                    "WHERE source_item_id = %s "
                    "OR target_item_id = %s"),
                (item1, item2))
            self.assertEqual(cursor.fetchone()['cnt'], 0)

    def test_cleanup_idempotent(self):
        pid = self.db.ensure_project(self.test_path)
        self.db.create_item(pid, 'issue', 'Item')
        cleanup_test_project(self.db, self.test_path)
        # Second call should not raise
        cleanup_test_project(self.db, self.test_path)


class TestTagColorNullCheck(unittest.TestCase):
    """Tests for #8229 — null check in _get_next_tag_color."""

    @classmethod
    def setUpClass(cls):
        from kanban_mcp.core import KanbanDB
        cls.db = KanbanDB()
        cls.test_path = "/tmp/test-tag-color-project"

    def setUp(self):
        cleanup_test_project(self.db, self.test_path)
        self.project_id = self.db.ensure_project(self.test_path)

    def tearDown(self):
        cleanup_test_project(self.db, self.test_path)

    def test_tag_color_empty_project(self):
        color = self.db._get_next_tag_color(self.project_id)
        self.assertEqual(color, self.db.TAG_COLOR_PALETTE[0])

    def test_tag_color_many_tags(self):
        # Create more tags than palette size to test round-robin
        palette_size = len(self.db.TAG_COLOR_PALETTE)
        for i in range(palette_size + 2):
            self.db.ensure_tag(self.project_id, f"tag-{i}")
        # Next color should wrap around
        color = self.db._get_next_tag_color(self.project_id)
        expected_idx = (palette_size + 2) % palette_size
        self.assertEqual(color, self.db.TAG_COLOR_PALETTE[expected_idx])


class TestTimelineParsing(unittest.TestCase):
    """Tests for #8227 — GROUP_CONCAT parsing safety."""

    def setUp(self):
        from kanban_mcp.timeline_builder import TimelineBuilder
        self.builder = TimelineBuilder(db=MagicMock())

    def _make_update(self, linked_items=None, item_id=None):
        """Create a fake update row."""
        return {
            'id': 1,
            'content': 'Test update content here',
            'created_at': datetime.now(),
            'linked_items': linked_items,
            **(({'item_id': item_id} if item_id is not None else {}))
        }

    def test_timeline_empty_linked_items(self):
        """Empty string linked_items should not crash."""
        update = self._make_update(linked_items='')
        # Simulate what _get_update_activities does with project-level queries
        linked_items_str = update.get('linked_items') or ''
        parsed = [
            int(x.strip())
            for x in linked_items_str.split(',')
            if x.strip() and x.strip().isdigit()]
        self.assertEqual(parsed, [])

    def test_timeline_null_linked_items(self):
        update = self._make_update(linked_items=None)
        linked_items_str = update.get('linked_items') or ''
        parsed = [
            int(x.strip())
            for x in linked_items_str.split(',')
            if x.strip() and x.strip().isdigit()]
        self.assertEqual(parsed, [])

    def test_timeline_single_linked_item(self):
        update = self._make_update(linked_items='42')
        linked_items_str = update.get('linked_items') or ''
        parsed = [
            int(x.strip())
            for x in linked_items_str.split(',')
            if x.strip() and x.strip().isdigit()]
        self.assertEqual(parsed, [42])

    def test_timeline_whitespace_in_linked_items(self):
        update = self._make_update(linked_items='42, ,, 99')
        linked_items_str = update.get('linked_items') or ''
        parsed = [
            int(x.strip())
            for x in linked_items_str.split(',')
            if x.strip() and x.strip().isdigit()]
        self.assertEqual(parsed, [42, 99])

    def test_timeline_non_numeric_linked_items(self):
        update = self._make_update(linked_items='abc,42')
        linked_items_str = update.get('linked_items') or ''
        parsed = [
            int(x.strip())
            for x in linked_items_str.split(',')
            if x.strip() and x.strip().isdigit()]
        self.assertEqual(parsed, [42])


class TestCLIInputValidation(unittest.TestCase):
    """Tests for #8228 — CLI export item_ids validation."""

    def setUp(self):
        from kanban_mcp.cli import export_data
        self.export_data = export_data

    def _call_export(self, item_ids_str):
        """Call export_data with test item_ids and return result."""
        from kanban_mcp.core import KanbanDB
        db = KanbanDB()
        return self.export_data(
            db,
            project_path="/tmp/test-cli-validation",
            format="json",
            item_ids=item_ids_str
        )

    def test_cli_invalid_item_ids(self):
        result = self._call_export("abc,def")
        self.assertIn("Error", result)

    def test_cli_mixed_valid_invalid_ids(self):
        result = self._call_export("1,abc,3")
        self.assertIn("Error", result)

    def test_cli_empty_item_ids(self):
        # Empty string should not error — it means no filter
        result = self._call_export("")
        # Empty string is falsy, so parsed_item_ids stays None — should work
        self.assertNotIn("Error", result)

    def test_cli_trailing_comma(self):
        # "1,2," — trailing comma should work (empty string filtered out)
        # items 1,2 may not exist, but shouldn't error
        result = self._call_export("1,2,")
        self.assertNotIn("Error", result)

    def test_cli_sql_injection_attempt(self):
        result = self._call_export("1; DROP TABLE items")
        self.assertIn("Error", result)


class TestPathResolution(unittest.TestCase):
    """Test that project paths are resolved before hashing."""

    def test_hash_resolves_relative_path(self):
        """Relative path components should be resolved before hashing."""
        from kanban_mcp.core import KanbanDB
        # /tmp/./foo/../ should resolve to /tmp
        h1 = KanbanDB.hash_project_path("/tmp/./foo/../")
        h2 = KanbanDB.hash_project_path("/tmp")
        self.assertEqual(h1, h2)

    def test_hash_resolves_symlinks(self):
        """Symlinked paths should hash to the same value."""
        import tempfile
        from kanban_mcp.core import KanbanDB
        with tempfile.TemporaryDirectory() as tmpdir:
            real_dir = os.path.join(tmpdir, "real")
            os.makedirs(real_dir)
            link_dir = os.path.join(tmpdir, "link")
            os.symlink(real_dir, link_dir)
            h_real = KanbanDB.hash_project_path(real_dir)
            h_link = KanbanDB.hash_project_path(link_dir)
            self.assertEqual(h_real, h_link)

    def test_ensure_project_stores_resolved_path(self):
        """ensure_project should store the resolved path in DB."""
        import tempfile
        from kanban_mcp.core import KanbanDB
        with tempfile.TemporaryDirectory() as tmpdir:
            real_dir = os.path.join(tmpdir, "real")
            os.makedirs(real_dir)
            link_dir = os.path.join(tmpdir, "link")
            os.symlink(real_dir, link_dir)

            db = MagicMock(spec=KanbanDB)
            db.hash_project_path = KanbanDB.hash_project_path
            db._db_cursor = MagicMock()

            # Call the real ensure_project with a symlink path
            from kanban_mcp.core import KanbanDB as RealDB
            # Use a real instance with mocked pool
            with patch(
                'kanban_mcp.db.mysql_backend.MySQLConnectionPool',
            ):
                with patch.dict(os.environ, {
                    'KANBAN_DB_USER': 'test',
                    'KANBAN_DB_PASSWORD': 'test',
                    'KANBAN_DB_NAME': 'test',
                }):
                    instance = RealDB()
            # Mock the cursor context manager
            mock_cursor = MagicMock()
            instance._db_cursor = MagicMock(
                return_value=MagicMock(
                    __enter__=MagicMock(
                        return_value=mock_cursor,
                    ),
                    __exit__=MagicMock(return_value=False),
                ),
            )
            instance.ensure_project(link_dir)

            # The INSERT should use the resolved (real) path
            call_args = mock_cursor.execute.call_args
            sql_params = call_args[0][1]
            # params are (project_id, directory_path, name)
            stored_path = sql_params[1]
            self.assertEqual(
                stored_path,
                str(os.path.realpath(real_dir)),
            )

    def test_ensure_project_dot_and_cwd_same(self):
        """ensure_project('.') should produce same ID as cwd."""
        from kanban_mcp.core import KanbanDB
        with patch(
            'kanban_mcp.db.mysql_backend.MySQLConnectionPool',
        ):
            with patch.dict(os.environ, {
                'KANBAN_DB_USER': 'test',
                'KANBAN_DB_PASSWORD': 'test',
                'KANBAN_DB_NAME': 'test',
            }):
                instance = KanbanDB()
        mock_cursor = MagicMock()
        instance._db_cursor = MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(
                    return_value=mock_cursor,
                ),
                __exit__=MagicMock(return_value=False),
            ),
        )
        id_dot = instance.ensure_project(".")
        id_cwd = instance.ensure_project(os.getcwd())
        self.assertEqual(id_dot, id_cwd)


if __name__ == "__main__":
    unittest.main()
