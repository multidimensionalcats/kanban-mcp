#!/usr/bin/env python3
"""
Unit tests for Kanban MCP Server.
Tests define target behavior - written BEFORE implementation.
"""

import unittest
import sys
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock, patch

# Import from kanban module (will exist after implementation)
sys.path.insert(0, str(Path(__file__).parent.parent))


def cleanup_test_project(db, project_path):
    """Clean up all test data for a project including the project itself."""
    project_id = db.hash_project_path(project_path)
    conn = db._get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM update_items WHERE update_id IN (SELECT id FROM updates WHERE project_id = %s)", (project_id,))
        cursor.execute("DELETE FROM updates WHERE project_id = %s", (project_id,))
        cursor.execute("DELETE FROM items WHERE project_id = %s", (project_id,))
        cursor.execute("DELETE FROM projects WHERE id = %s", (project_id,))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


class TestKanbanDB(unittest.TestCase):
    """Test the KanbanDB database operations."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test database connection."""
        from kanban_mcp import KanbanDB
        cls.db = KanbanDB()
        # Use a test project path
        cls.test_project_path = "/tmp/test-kanban-project"
        cls.test_project_id = cls.db.hash_project_path(cls.test_project_path)
    
    def setUp(self):
        """Ensure clean state before each test."""
        from kanban_mcp import KanbanDB
        self.db = KanbanDB()
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
        project_id = self.db.ensure_project(self.test_project_path, "test-project")
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
        """Todos should skip review status (todo workflow: backlog->todo->in_progress->done)."""
        self.db.ensure_project(self.test_project_path)
        item_id = self.db.create_item(
            project_id=self.test_project_id,
            type_name="todo",
            title="Test Todo"
        )
        
        self.db.advance_status(item_id)  # backlog -> todo
        self.db.advance_status(item_id)  # todo -> in_progress
        result = self.db.advance_status(item_id)  # in_progress -> done (not review)
        
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
        
        issues = self.db.list_items(project_id=self.test_project_id, type_name="issue")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]['type_name'], 'issue')
    
    def test_list_items_by_status(self):
        """list_items should filter by status."""
        self.db.ensure_project(self.test_project_path)
        item1 = self.db.create_item(self.test_project_id, "issue", "Issue 1")
        self.db.create_item(self.test_project_id, "issue", "Issue 2")
        self.db.advance_status(item1)  # Move to todo
        
        backlog_items = self.db.list_items(project_id=self.test_project_id, status_name="backlog")
        self.assertEqual(len(backlog_items), 1)
    
    def test_get_backlog_items(self):
        """Should be able to get items in backlog status."""
        self.db.ensure_project(self.test_project_path)
        self.db.create_item(self.test_project_id, "issue", "Backlog Issue")
        item2 = self.db.create_item(self.test_project_id, "todo", "In Progress Todo")
        self.db.advance_status(item2)  # backlog -> todo
        self.db.advance_status(item2)  # todo -> in_progress
        
        backlog = self.db.list_items(project_id=self.test_project_id, status_name="backlog")
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
        
        update_id = self.db.add_update(
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
    
    def setUp(self):
        from kanban_mcp import KanbanMCPServer
        self.server = KanbanMCPServer()
        self.test_project_path = "/tmp/test-kanban-mcp"
        cleanup_test_project(self.server.db, self.test_project_path)
    
    def tearDown(self):
        cleanup_test_project(self.server.db, self.test_project_path)
    
    def test_no_project_set_initially(self):
        """Server should have no current project initially."""
        self.assertIsNone(self.server.current_project_id)
    
    def test_set_current_project(self):
        """set_current_project should store project in server state."""
        result = self.server.tools['set_current_project']['function'](self.test_project_path)
        self.assertTrue(result['success'])
        self.assertIsNotNone(self.server.current_project_id)
    
    def test_get_current_project(self):
        """get_current_project should return current project info."""
        self.server.tools['set_current_project']['function'](self.test_project_path)
        result = self.server.tools['get_current_project']['function']()
        self.assertTrue(result['success'])
        self.assertEqual(result['directory_path'], self.test_project_path)
    
    def test_tools_use_current_project_when_not_specified(self):
        """Tools should use current project when project_dir not specified."""
        self.server.tools['set_current_project']['function'](self.test_project_path)
        
        # Create item without specifying project_dir
        result = self.server.tools['new_item']['function'](
            item_type="issue",
            title="Test Issue"
        )
        self.assertTrue(result['success'])


class TestJSONRPCProtocol(unittest.TestCase):
    """Test JSON-RPC protocol handling."""
    
    def setUp(self):
        from kanban_mcp import KanbanMCPServer
        self.server = KanbanMCPServer()
        self.test_project_path = "/tmp/test-jsonrpc"
        cleanup_test_project(self.server.db, self.test_project_path)
    
    def tearDown(self):
        cleanup_test_project(self.server.db, self.test_project_path)
    
    def test_initialize_response(self):
        """Initialize should return proper protocol info."""
        import asyncio
        request = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
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
        request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
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
            "params": {"name": "set_current_project", "arguments": {"project_dir": self.test_project_path}}
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
        request = {"jsonrpc": "2.0", "id": 5, "method": "unknown/method", "params": {}}
        response = asyncio.run(self.server.handle_request(request))
        
        self.assertIn('error', response)
        self.assertEqual(response['error']['code'], -32601)


class TestGetTodos(unittest.TestCase):
    """Test get_todos tool specifically."""
    
    def setUp(self):
        from kanban_mcp import KanbanMCPServer
        self.server = KanbanMCPServer()
        self.test_project_path = "/tmp/test-get-todos"
        cleanup_test_project(self.server.db, self.test_project_path)
        # Set current project
        self.server.tools['set_current_project']['function'](self.test_project_path)
    
    def tearDown(self):
        cleanup_test_project(self.server.db, self.test_project_path)
    
    def test_get_todos_returns_backlog_items(self):
        """get_todos should return items in backlog status."""
        # Create items
        self.server.tools['new_item']['function'](item_type="issue", title="Backlog Issue")
        result = self.server.tools['new_item']['function'](item_type="todo", title="In Progress Todo")
        # Move one to in_progress
        item_id = result['item']['id']
        self.server.tools['advance_status']['function'](item_id)  # backlog -> todo
        self.server.tools['advance_status']['function'](item_id)  # todo -> in_progress
        
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
    
    def setUp(self):
        from kanban_mcp import KanbanDB
        self.db = KanbanDB()
        self.test_project_path = "/tmp/test-pool"
        cleanup_test_project(self.db, self.test_project_path)
    
    def tearDown(self):
        cleanup_test_project(self.db, self.test_project_path)
        # Ensure pool is cleaned up
        if hasattr(self.db, '_pool') and self.db._pool:
            try:
                pass  # Pool auto-manages connections, no explicit close needed
            except:
                pass
    
    def test_db_has_pool(self):
        """KanbanDB should have a connection pool."""
        self.assertTrue(hasattr(self.db, '_pool'))
        self.assertIsNotNone(self.db._pool)
    
    def test_get_connection_returns_pooled_connection(self):
        """_get_connection should return connection from pool."""
        conn = self.db._get_connection()
        self.assertIsNotNone(conn)
        # Pooled connections have pool_config attribute
        self.assertTrue(hasattr(conn, '_pool_config_version') or conn.is_connected())
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
        items = self.db.list_items(project_id=self.db.hash_project_path(self.test_project_path))
        self.assertEqual(len(items), 10)
    
    def test_pool_size_configurable(self):
        """Pool size should be configurable at init."""
        from kanban_mcp import KanbanDB
        db = KanbanDB(pool_size=3)
        self.assertEqual(db._pool.pool_size, 3)
        # Pool auto-manages connections, no explicit close needed
    
    def test_concurrent_connections_within_pool_limit(self):
        """Should handle concurrent operations within pool limit."""
        self.db.ensure_project(self.test_project_path)
        project_id = self.db.hash_project_path(self.test_project_path)
        
        # Create several items rapidly
        item_ids = []
        for i in range(5):
            item_id = self.db.create_item(project_id, "issue", f"Concurrent {i}")
            item_ids.append(item_id)
        
        # Verify all were created
        for item_id in item_ids:
            item = self.db.get_item(item_id)
            self.assertIsNotNone(item)
