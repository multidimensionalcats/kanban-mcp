#!/usr/bin/env python3
"""
Kanban MCP Server for Claude Code
A centralized issue/todo/feature/diary tracking system using MySQL.
"""

import asyncio
import os
import sys
import json
import hashlib
import inspect
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

import mysql.connector
from mysql.connector import Error
from mysql.connector.pooling import MySQLConnectionPool


class KanbanDB:
    """Database operations for kanban system."""
    
    def __init__(self, host: str = None, user: str = None, 
                 password: str = None, database: str = None,
                 pool_size: int = 5):
        self.config = {
            "host": host or os.environ.get("KANBAN_DB_HOST", "localhost"),
            "user": user or os.environ.get("KANBAN_DB_USER", ""),
            "password": password or os.environ.get("KANBAN_DB_PASSWORD", ""),
            "database": database or os.environ.get("KANBAN_DB_NAME", ""),
        }
        self._pool = MySQLConnectionPool(
            pool_name="kanban_pool",
            pool_size=pool_size,
            **self.config
        )
    
    def _get_connection(self):
        """Get a database connection from the pool."""
        return self._pool.get_connection()
    
    @staticmethod
    def hash_project_path(directory_path: str) -> str:
        """Generate a 16-char hash ID from directory path."""
        return hashlib.sha256(directory_path.encode()).hexdigest()[:16]
    
    def ensure_project(self, directory_path: str, name: str = None) -> str:
        """Ensure project exists, create if not. Returns project_id."""
        project_id = self.hash_project_path(directory_path)
        if name is None:
            name = Path(directory_path).name
        
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT IGNORE INTO projects (id, directory_path, name) VALUES (%s, %s, %s)",
                (project_id, directory_path, name)
            )
            conn.commit()
            return project_id
        finally:
            cursor.close()
            conn.close()
    
    def get_project_by_path(self, directory_path: str) -> Optional[Dict]:
        """Get project by directory path."""
        project_id = self.hash_project_path(directory_path)
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM projects WHERE id = %s", (project_id,))
            return cursor.fetchone()
        finally:
            cursor.close()
            conn.close()
    
    def get_project_by_id(self, project_id: str) -> Optional[Dict]:
        """Get project by ID."""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM projects WHERE id = %s", (project_id,))
            return cursor.fetchone()
        finally:
            cursor.close()
            conn.close()
    
    def get_type_id(self, type_name: str) -> int:
        """Get item_type id by name."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id FROM item_types WHERE name = %s", (type_name,))
            result = cursor.fetchone()
            if result:
                return result[0]
            raise ValueError(f"Unknown item type: {type_name}")
        finally:
            cursor.close()
            conn.close()
    
    def get_status_id(self, status_name: str) -> int:
        """Get status id by name."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id FROM statuses WHERE name = %s", (status_name,))
            result = cursor.fetchone()
            if result:
                return result[0]
            raise ValueError(f"Unknown status: {status_name}")
        finally:
            cursor.close()
            conn.close()
    
    def get_default_status_for_type(self, type_id: int) -> int:
        """Get the first status in workflow for a type."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT status_id FROM type_status_workflow WHERE type_id = %s ORDER BY sequence LIMIT 1",
                (type_id,)
            )
            result = cursor.fetchone()
            if result:
                return result[0]
            raise ValueError(f"No workflow defined for type_id: {type_id}")
        finally:
            cursor.close()
            conn.close()
    
    def create_item(self, project_id: str, type_name: str, title: str, 
                    description: str = None, priority: int = 3, status_name: str = None) -> int:
        """Create a new item. Returns item id."""
        type_id = self.get_type_id(type_name)
        
        if status_name:
            status_id = self.get_status_id(status_name)
        else:
            status_id = self.get_default_status_for_type(type_id)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """INSERT INTO items (project_id, type_id, status_id, title, description, priority)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (project_id, type_id, status_id, title, description, priority)
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            cursor.close()
            conn.close()
    
    def get_item(self, item_id: int) -> Optional[Dict]:
        """Get item with type and status names."""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT i.*, it.name as type_name, s.name as status_name, p.name as project_name
                FROM items i
                JOIN item_types it ON i.type_id = it.id
                JOIN statuses s ON i.status_id = s.id
                JOIN projects p ON i.project_id = p.id
                WHERE i.id = %s
            """, (item_id,))
            return cursor.fetchone()
        finally:
            cursor.close()
            conn.close()
    
    def list_items(self, project_id: str = None, type_name: str = None, 
                   status_name: str = None, limit: int = 50) -> List[Dict]:
        """List items with optional filters."""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            query = """
                SELECT i.*, it.name as type_name, s.name as status_name, p.name as project_name
                FROM items i
                JOIN item_types it ON i.type_id = it.id
                JOIN statuses s ON i.status_id = s.id
                JOIN projects p ON i.project_id = p.id
                WHERE 1=1
            """
            params = []
            
            if project_id:
                query += " AND i.project_id = %s"
                params.append(project_id)
            if type_name:
                query += " AND it.name = %s"
                params.append(type_name)
            if status_name:
                query += " AND s.name = %s"
                params.append(status_name)
            
            query += " ORDER BY i.priority ASC, i.created_at DESC LIMIT %s"
            params.append(limit)
            
            cursor.execute(query, params)
            return cursor.fetchall()
        finally:
            cursor.close()
            conn.close()
    
    def advance_status(self, item_id: int) -> Dict:
        """Move item to next status in workflow. Returns new status info."""
        item = self.get_item(item_id)
        if not item:
            raise ValueError(f"Item not found: {item_id}")
        
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT tsw.sequence, tsw.status_id
                FROM type_status_workflow tsw
                WHERE tsw.type_id = %s AND tsw.status_id = %s
            """, (item['type_id'], item['status_id']))
            current = cursor.fetchone()
            
            if not current:
                raise ValueError("Current status not in workflow")
            
            cursor.execute("""
                SELECT tsw.status_id, s.name as status_name
                FROM type_status_workflow tsw
                JOIN statuses s ON tsw.status_id = s.id
                WHERE tsw.type_id = %s AND tsw.sequence > %s
                ORDER BY tsw.sequence LIMIT 1
            """, (item['type_id'], current['sequence']))
            next_status = cursor.fetchone()
            
            if not next_status:
                return {"success": False, "message": "Already at final status", "current_status": item['status_name']}
            
            cursor.execute(
                "UPDATE items SET status_id = %s WHERE id = %s",
                (next_status['status_id'], item_id)
            )
            conn.commit()
            
            return {
                "success": True, 
                "previous_status": item['status_name'],
                "new_status": next_status['status_name']
            }
        finally:
            cursor.close()
            conn.close()
    
    def revert_status(self, item_id: int) -> Dict:
        """Move item to previous status in workflow. Returns new status info."""
        item = self.get_item(item_id)
        if not item:
            raise ValueError(f"Item not found: {item_id}")
        
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT tsw.sequence, tsw.status_id
                FROM type_status_workflow tsw
                WHERE tsw.type_id = %s AND tsw.status_id = %s
            """, (item['type_id'], item['status_id']))
            current = cursor.fetchone()
            
            if not current:
                raise ValueError("Current status not in workflow")
            
            cursor.execute("""
                SELECT tsw.status_id, s.name as status_name
                FROM type_status_workflow tsw
                JOIN statuses s ON tsw.status_id = s.id
                WHERE tsw.type_id = %s AND tsw.sequence < %s
                ORDER BY tsw.sequence DESC LIMIT 1
            """, (item['type_id'], current['sequence']))
            prev_status = cursor.fetchone()
            
            if not prev_status:
                return {"success": False, "message": "Already at first status", "current_status": item['status_name']}
            
            cursor.execute(
                "UPDATE items SET status_id = %s WHERE id = %s",
                (prev_status['status_id'], item_id)
            )
            conn.commit()
            
            return {
                "success": True, 
                "previous_status": item['status_name'],
                "new_status": prev_status['status_name']
            }
        finally:
            cursor.close()
            conn.close()
    
    def set_status(self, item_id: int, status_name: str) -> Dict:
        """Set item to specific status (must be valid for type)."""
        item = self.get_item(item_id)
        if not item:
            raise ValueError(f"Item not found: {item_id}")
        
        status_id = self.get_status_id(status_name)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT 1 FROM type_status_workflow 
                WHERE type_id = %s AND status_id = %s
            """, (item['type_id'], status_id))
            if not cursor.fetchone():
                raise ValueError(f"Status '{status_name}' not valid for type '{item['type_name']}'")
            
            closed_at = "NOW()" if status_name in ('done', 'closed') else "NULL"
            cursor.execute(
                f"UPDATE items SET status_id = %s, closed_at = {closed_at} WHERE id = %s",
                (status_id, item_id)
            )
            conn.commit()
            
            return {
                "success": True,
                "previous_status": item['status_name'],
                "new_status": status_name
            }
        finally:
            cursor.close()
            conn.close()
    
    def close_item(self, item_id: int) -> Dict:
        """Mark item as done/closed."""
        item = self.get_item(item_id)
        if not item:
            raise ValueError(f"Item not found: {item_id}")
        
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT s.id, s.name
                FROM type_status_workflow tsw
                JOIN statuses s ON tsw.status_id = s.id
                WHERE tsw.type_id = %s
                ORDER BY tsw.sequence DESC LIMIT 1
            """, (item['type_id'],))
            final_status = cursor.fetchone()
            
            cursor.execute(
                "UPDATE items SET status_id = %s, closed_at = NOW() WHERE id = %s",
                (final_status['id'], item_id)
            )
            conn.commit()
            
            return {
                "success": True,
                "previous_status": item['status_name'],
                "new_status": final_status['name']
            }
        finally:
            cursor.close()
            conn.close()
    
    def delete_item(self, item_id: int) -> Dict:
        """Delete an item."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM items WHERE id = %s", (item_id,))
            conn.commit()
            return {"success": True, "deleted_id": item_id, "rows_affected": cursor.rowcount}
        finally:
            cursor.close()
            conn.close()
    
    def add_update(self, project_id: str, content: str, item_ids: List[int] = None) -> int:
        """Add an update, optionally linked to items. Returns update id."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO updates (project_id, content) VALUES (%s, %s)",
                (project_id, content)
            )
            update_id = cursor.lastrowid
            
            if item_ids:
                for item_id in item_ids:
                    cursor.execute(
                        "INSERT INTO update_items (update_id, item_id) VALUES (%s, %s)",
                        (update_id, item_id)
                    )
            
            conn.commit()
            return update_id
        finally:
            cursor.close()
            conn.close()
    
    def get_latest_update(self, project_id: str) -> Optional[Dict]:
        """Get most recent update for a project."""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT u.*, GROUP_CONCAT(ui.item_id) as item_ids
                FROM updates u
                LEFT JOIN update_items ui ON u.id = ui.update_id
                WHERE u.project_id = %s
                GROUP BY u.id
                ORDER BY u.id DESC
                LIMIT 1
            """, (project_id,))
            result = cursor.fetchone()
            if result and result['item_ids']:
                result['item_ids'] = [int(x) for x in result['item_ids'].split(',')]
            return result
        finally:
            cursor.close()
            conn.close()
    
    def get_updates(self, project_id: str, limit: int = 20) -> List[Dict]:
        """Get recent updates for a project."""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT u.*, GROUP_CONCAT(ui.item_id) as item_ids
                FROM updates u
                LEFT JOIN update_items ui ON u.id = ui.update_id
                WHERE u.project_id = %s
                GROUP BY u.id
                ORDER BY u.id DESC
                LIMIT %s
            """, (project_id, limit))
            results = cursor.fetchall()
            for r in results:
                if r['item_ids']:
                    r['item_ids'] = [int(x) for x in r['item_ids'].split(',')]
            return results
        finally:
            cursor.close()
            conn.close()
    
    def project_summary(self, project_id: str) -> Dict:
        """Get summary counts by type and status for a project."""
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT it.name as type_name, s.name as status_name, COUNT(*) as count
                FROM items i
                JOIN item_types it ON i.type_id = it.id
                JOIN statuses s ON i.status_id = s.id
                WHERE i.project_id = %s
                GROUP BY it.name, s.name
                ORDER BY it.name, s.name
            """, (project_id,))
            
            results = cursor.fetchall()
            summary = {}
            for row in results:
                type_name = row['type_name']
                if type_name not in summary:
                    summary[type_name] = {}
                summary[type_name][row['status_name']] = row['count']
            
            return summary
        finally:
            cursor.close()
            conn.close()


class KanbanMCPServer:
    """MCP Server for Kanban system."""
    
    def __init__(self, name: str = "kanban-mcp", version: str = "1.0.0"):
        self.name = name
        self.version = version
        self.tools = {}
        self.db = KanbanDB()
        
        # Current project state
        self.current_project_id = None
        self.current_project_path = None
        
        # Setup logging
        log_dir = Path.home() / ".kanban_mcp"
        log_dir.mkdir(exist_ok=True)
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[logging.FileHandler(log_dir / 'kanban_server.log')]
        )
        self.logger = logging.getLogger(self.name)
        
        self._register_tools()
        self.logger.info("Kanban MCP Server initialized")
    
    def _get_project_id(self, project_dir: str = None) -> str:
        """Get project ID from explicit path, env vars, or current project state.
        
        Priority:
        1. Explicit project_dir parameter
        2. KANBAN_PROJECT_DIR env var (explicitly passed in MCP config)
        3. CLAUDE_PROJECT_DIR env var (may be inherited from Claude Code)
        4. Stored state (current_project_id)
        5. Error
        """
        if project_dir:
            return self.db.ensure_project(project_dir)
        
        # Check environment variables
        env_project_dir = os.environ.get('KANBAN_PROJECT_DIR') or os.environ.get('CLAUDE_PROJECT_DIR')
        if env_project_dir:
            return self.db.ensure_project(env_project_dir)
        
        if self.current_project_id:
            return self.current_project_id
        
        raise ValueError(
            "No project specified. Set KANBAN_PROJECT_DIR env var in MCP config, "
            "or call set_current_project first."
        )
    
    def tool(self, name: str):
        """Decorator to register tools."""
        def decorator(func):
            sig = inspect.signature(func)
            properties = {}
            required = []
            
            for param_name, param in sig.parameters.items():
                param_type = "string"
                if param.annotation == int:
                    param_type = "integer"
                elif param.annotation == bool:
                    param_type = "boolean"
                elif param.annotation == float:
                    param_type = "number"
                
                properties[param_name] = {
                    "type": param_type,
                    "description": f"{param_name} parameter"
                }
                
                if param.default == inspect.Parameter.empty:
                    required.append(param_name)
            
            self.tools[name] = {
                "function": func,
                "description": func.__doc__.strip() if func.__doc__ else name,
                "inputSchema": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
            return func
        return decorator
    
    def _serialize_result(self, obj):
        """Convert result to JSON-serializable format."""
        if isinstance(obj, dict):
            return {k: self._serialize_result(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._serialize_result(item) for item in obj]
        elif isinstance(obj, datetime):
            return obj.isoformat()
        else:
            return obj
    
    def _register_tools(self):
        """Register all kanban tools."""
        
        # --- Project Context Tools ---
        
        @self.tool("set_current_project")
        def set_current_project(project_dir: str) -> Dict[str, Any]:
            """Set the current project context. Called at session start with $PWD."""
            self.current_project_id = self.db.ensure_project(project_dir)
            self.current_project_path = project_dir
            project = self.db.get_project_by_id(self.current_project_id)
            return {
                "success": True, 
                "project_id": self.current_project_id,
                "project_name": project['name'] if project else None,
                "directory_path": project_dir
            }
        
        @self.tool("get_current_project")
        def get_current_project() -> Dict[str, Any]:
            """Get the current project context."""
            if not self.current_project_id:
                return {"success": False, "error": "No current project set"}
            project = self.db.get_project_by_id(self.current_project_id)
            return {
                "success": True,
                "project_id": self.current_project_id,
                "project_name": project['name'] if project else None,
                "directory_path": self.current_project_path
            }
        
        # --- Item Creation/Management ---
        
        @self.tool("new_item")
        def new_item(item_type: str, title: str, 
                     description: str = "", priority: int = 3) -> Dict[str, Any]:
            """Create a new issue, todo, feature, or diary entry for current project."""
            project_id = self._get_project_id()
            item_id = self.db.create_item(
                project_id=project_id,
                type_name=item_type,
                title=title,
                description=description if description else None,
                priority=priority
            )
            item = self.db.get_item(item_id)
            return {"success": True, "item": self._serialize_result(item)}
        
        @self.tool("list_items")
        def list_items(item_type: str = "", status: str = "", 
                       limit: int = 50) -> Dict[str, Any]:
            """List items for current project with optional type/status filters."""
            project_id = self._get_project_id()
            items = self.db.list_items(
                project_id=project_id,
                type_name=item_type if item_type else None,
                status_name=status if status else None,
                limit=limit
            )
            return {"success": True, "items": self._serialize_result(items), "count": len(items)}
        
        @self.tool("get_item")
        def get_item(item_id: int) -> Dict[str, Any]:
            """Get full details of a specific item."""
            item = self.db.get_item(item_id)
            if item:
                return {"success": True, "item": self._serialize_result(item)}
            return {"success": False, "error": "Item not found"}
        
        @self.tool("advance_status")
        def advance_status(item_id: int) -> Dict[str, Any]:
            """Move item to next status in its workflow."""
            result = self.db.advance_status(item_id)
            return self._serialize_result(result)
        
        @self.tool("revert_status")
        def revert_status(item_id: int) -> Dict[str, Any]:
            """Move item to previous status in its workflow."""
            result = self.db.revert_status(item_id)
            return self._serialize_result(result)
        
        @self.tool("set_status")
        def set_status(item_id: int, status: str) -> Dict[str, Any]:
            """Set item to a specific status (must be valid for item type)."""
            result = self.db.set_status(item_id, status)
            return self._serialize_result(result)
        
        @self.tool("close_item")
        def close_item(item_id: int) -> Dict[str, Any]:
            """Mark item as done/closed."""
            result = self.db.close_item(item_id)
            return self._serialize_result(result)
        
        @self.tool("delete_item")
        def delete_item(item_id: int) -> Dict[str, Any]:
            """Permanently delete an item."""
            result = self.db.delete_item(item_id)
            return self._serialize_result(result)
        
        # --- Updates/Progress ---
        
        @self.tool("add_update")
        def add_update(content: str, item_ids: str = "") -> Dict[str, Any]:
            """Add a progress update, optionally linked to items (comma-separated IDs)."""
            project_id = self._get_project_id()
            linked_ids = [int(x.strip()) for x in item_ids.split(',') if x.strip()] if item_ids else None
            update_id = self.db.add_update(project_id, content, linked_ids)
            return {"success": True, "update_id": update_id}
        
        @self.tool("get_latest_update")
        def get_latest_update() -> Dict[str, Any]:
            """Get the most recent update for current project."""
            project_id = self._get_project_id()
            update = self.db.get_latest_update(project_id)
            if update:
                return {"success": True, "update": self._serialize_result(update)}
            return {"success": False, "error": "No updates found"}
        
        @self.tool("get_updates")
        def get_updates(limit: int = 20) -> Dict[str, Any]:
            """Get recent updates for current project."""
            project_id = self._get_project_id()
            updates = self.db.get_updates(project_id, limit)
            return {"success": True, "updates": self._serialize_result(updates), "count": len(updates)}
        
        # --- Summary/Query Tools ---
        
        @self.tool("project_summary")
        def project_summary() -> Dict[str, Any]:
            """Get summary of items by type and status for current project."""
            project_id = self._get_project_id()
            summary = self.db.project_summary(project_id)
            return {"success": True, "summary": summary}
        
        @self.tool("get_active_items")
        def get_active_items() -> Dict[str, Any]:
            """Get items in 'in_progress' status for context during work."""
            project_id = self._get_project_id()
            items = self.db.list_items(project_id=project_id, status_name="in_progress", limit=20)
            return {"success": True, "items": self._serialize_result(items), "count": len(items)}
        
        @self.tool("get_todos")
        def get_todos() -> Dict[str, Any]:
            """Get items in 'backlog' status - the todo queue for current project."""
            project_id = self._get_project_id()
            items = self.db.list_items(project_id=project_id, status_name="backlog", limit=50)
            return {"success": True, "items": self._serialize_result(items), "count": len(items)}
    
    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MCP JSON-RPC request."""
        try:
            method = request.get("method")
            params = request.get("params", {})
            
            self.logger.info(f"Request: method={method}, id={request.get('id')}")
            
            if method == "initialize":
                return {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": self.name,
                            "version": self.version
                        }
                    }
                }
            
            elif method == "tools/list":
                tools_list = [
                    {
                        "name": name,
                        "description": tool_data["description"],
                        "inputSchema": tool_data["inputSchema"]
                    }
                    for name, tool_data in self.tools.items()
                ]
                return {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "result": {"tools": tools_list}
                }
            
            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                
                self.logger.info(f"Tool call: {tool_name}")
                
                if tool_name not in self.tools:
                    return {
                        "jsonrpc": "2.0",
                        "id": request.get("id"),
                        "error": {"code": -32602, "message": f"Unknown tool: {tool_name}"}
                    }
                
                try:
                    result = self.tools[tool_name]["function"](**arguments)
                    return {
                        "jsonrpc": "2.0",
                        "id": request.get("id"),
                        "result": {
                            "content": [{"type": "text", "text": json.dumps(result, indent=2)}]
                        }
                    }
                except Exception as e:
                    self.logger.error(f"Tool error: {e}", exc_info=True)
                    return {
                        "jsonrpc": "2.0",
                        "id": request.get("id"),
                        "error": {"code": -32603, "message": f"Tool execution failed: {str(e)}"}
                    }
            
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "error": {"code": -32601, "message": f"Method not found: {method}"}
                }
        
        except Exception as e:
            self.logger.error(f"Request error: {e}", exc_info=True)
            return {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {"code": -32603, "message": f"Internal error: {str(e)}"}
            }
    
    async def run(self):
        """Main server loop - STDIO JSON-RPC."""
        self.logger.info(f"Starting {self.name} server")
        
        try:
            while True:
                line = sys.stdin.readline()
                if not line:
                    self.logger.info("EOF, stopping server")
                    break
                
                try:
                    request = json.loads(line.strip())
                    response = await self.handle_request(request)
                    
                    if 'id' not in request:
                        continue  # Notification, no response
                    
                    print(json.dumps(response), flush=True)
                    
                except json.JSONDecodeError as e:
                    self.logger.error(f"JSON decode error: {e}")
                    print(json.dumps({
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32700, "message": f"Parse error: {str(e)}"}
                    }), flush=True)
        
        except KeyboardInterrupt:
            self.logger.info("Server stopped by user")
        except Exception as e:
            self.logger.error(f"Server error: {e}", exc_info=True)


def main():
    """Main entry point."""
    server = KanbanMCPServer()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
