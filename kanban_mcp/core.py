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
import struct
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path
from contextlib import contextmanager

import mysql.connector
from mysql.connector import Error
from mysql.connector.pooling import MySQLConnectionPool
try:
    import numpy as np
except ImportError:
    np = None

from kanban_mcp.export import ExportBuilder, export_to_format

# Load .env file if present (looks in CWD and script directory)
try:
    from dotenv import load_dotenv
    load_dotenv()  # CWD
    load_dotenv(Path(__file__).parent / '.env')  # script directory
except ImportError:
    pass

logger = logging.getLogger(__name__)

# Lazy imports for embedding - only loaded when needed
_onnx_session = None
_tokenizer = None


class KanbanDB:
    """Database operations for kanban system."""

    # Predefined color palette for auto-assignment to tags
    _pool_counter = 0

    TAG_COLOR_PALETTE = [
        '#4ade80',  # Green
        '#60a5fa',  # Blue
        '#f87171',  # Red
        '#a78bfa',  # Purple
        '#fbbf24',  # Yellow
        '#fb923c',  # Orange
        '#ec4899',  # Pink
        '#14b8a6',  # Teal
        '#8b5cf6',  # Violet
        '#f59e0b',  # Amber
        '#06b6d4',  # Cyan
        '#84cc16',  # Lime
    ]

    def __init__(self, host: str = None, user: str = None,
                 password: str = None, database: str = None,
                 pool_size: int = None):
        resolved_user = user or os.environ.get("KANBAN_DB_USER", "")
        resolved_password = password or os.environ.get("KANBAN_DB_PASSWORD", "")
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
                f"Missing required database credentials: {', '.join(missing)}. "
                "Set them as environment variables or pass to constructor."
            )

        self.config = {
            "host": host or os.environ.get("KANBAN_DB_HOST", "localhost"),
            "user": resolved_user,
            "password": resolved_password,
            "database": resolved_database,
        }
        if pool_size is None:
            pool_size = int(os.environ.get("KANBAN_DB_POOL_SIZE", "5"))

        KanbanDB._pool_counter += 1
        self._pool = MySQLConnectionPool(
            pool_name=f"kanban_pool_{KanbanDB._pool_counter}",
            pool_size=pool_size,
            **self.config
        )
    
    def _get_connection(self):
        """Get a database connection from the pool."""
        return self._pool.get_connection()

    @contextmanager
    def _db_cursor(self, dictionary: bool = False, commit: bool = False):
        """Context manager for database cursor with automatic cleanup.

        Args:
            dictionary: If True, return rows as dicts. If False, return tuples.
            commit: If True, commit transaction on successful exit.

        Yields:
            cursor: MySQL cursor object

        Example:
            # Read operation
            with self._db_cursor(dictionary=True) as cursor:
                cursor.execute("SELECT * FROM items WHERE id = %s", (item_id,))
                return cursor.fetchone()

            # Write operation
            with self._db_cursor(commit=True) as cursor:
                cursor.execute("INSERT INTO items ...", params)
                item_id = cursor.lastrowid
        """
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

    def _safe_embedding_op(self, op: str, source_type: str, source_id: int):
        """Run embedding op with debug logging on failure."""
        try:
            getattr(self, op)(source_type, source_id)
        except Exception:
            logger.debug("Embedding %s failed for %s:%s", op, source_type, source_id, exc_info=True)

    @staticmethod
    def hash_project_path(directory_path: str) -> str:
        """Generate a 16-char hash ID from directory path."""
        return hashlib.sha256(directory_path.encode()).hexdigest()[:16]
    
    def ensure_project(self, directory_path: str, name: str = None) -> str:
        """Ensure project exists, create if not. Returns project_id."""
        project_id = self.hash_project_path(directory_path)
        if name is None:
            name = Path(directory_path).name

        with self._db_cursor(commit=True) as cursor:
            cursor.execute(
                "INSERT IGNORE INTO projects (id, directory_path, name) VALUES (%s, %s, %s)",
                (project_id, directory_path, name)
            )
            return project_id
    
    def get_project_by_path(self, directory_path: str) -> Optional[Dict]:
        """Get project by directory path."""
        project_id = self.hash_project_path(directory_path)
        with self._db_cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM projects WHERE id = %s", (project_id,))
            return cursor.fetchone()

    def get_project_by_id(self, project_id: str) -> Optional[Dict]:
        """Get project by ID."""
        with self._db_cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM projects WHERE id = %s", (project_id,))
            return cursor.fetchone()

    def get_type_id(self, type_name: str) -> int:
        """Get item_type id by name."""
        with self._db_cursor() as cursor:
            cursor.execute("SELECT id FROM item_types WHERE name = %s", (type_name,))
            result = cursor.fetchone()
            if result:
                return result[0]
            raise ValueError(f"Unknown item type: {type_name}")

    def get_status_id(self, status_name: str) -> int:
        """Get status id by name."""
        with self._db_cursor() as cursor:
            cursor.execute("SELECT id FROM statuses WHERE name = %s", (status_name,))
            result = cursor.fetchone()
            if result:
                return result[0]
            raise ValueError(f"Unknown status: {status_name}")
    
    def get_default_status_for_type(self, type_id: int) -> int:
        """Get the first status in workflow for a type."""
        with self._db_cursor() as cursor:
            cursor.execute(
                "SELECT status_id FROM type_status_workflow WHERE type_id = %s ORDER BY sequence LIMIT 1",
                (type_id,)
            )
            result = cursor.fetchone()
            if result:
                return result[0]
            raise ValueError(f"No workflow defined for type_id: {type_id}")

    def create_item(self, project_id: str, type_name: str, title: str,
                    description: str = None, priority: int = 3,
                    complexity: int = None, status_name: str = None,
                    parent_id: int = None) -> int:
        """Create a new item. Returns item id."""
        # Validate complexity if provided
        if complexity is not None and (complexity < 1 or complexity > 5):
            raise ValueError(f"Complexity must be 1-5, got {complexity}")

        # Validate parent_id if provided
        if parent_id is not None:
            parent = self.get_item(parent_id)
            if not parent:
                raise ValueError(f"Parent item not found: {parent_id}")
            if parent['project_id'] != project_id:
                raise ValueError("Parent item must be in the same project")

        type_id = self.get_type_id(type_name)

        if status_name:
            status_id = self.get_status_id(status_name)
        else:
            status_id = self.get_default_status_for_type(type_id)

        with self._db_cursor(commit=True) as cursor:
            cursor.execute(
                """INSERT INTO items (project_id, type_id, status_id, title, description, priority, complexity, parent_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (project_id, type_id, status_id, title, description, priority, complexity, parent_id)
            )
            item_id = cursor.lastrowid

        # Record initial status in history
        self._record_status_change(item_id, None, status_id, 'create')

        # Auto-generate embedding (non-blocking, errors logged)
        self._safe_embedding_op('upsert_embedding', 'item', item_id)

        return item_id

    def get_item(self, item_id: int) -> Optional[Dict]:
        """Get item with type and status names."""
        with self._db_cursor(dictionary=True) as cursor:
            cursor.execute("""
                SELECT i.*, it.name as type_name, s.name as status_name, p.name as project_name
                FROM items i
                JOIN item_types it ON i.type_id = it.id
                JOIN statuses s ON i.status_id = s.id
                JOIN projects p ON i.project_id = p.id
                WHERE i.id = %s
            """, (item_id,))
            result = cursor.fetchone()
            # Ensure parent_id is included (may be NULL)
            if result and 'parent_id' not in result:
                result['parent_id'] = None
            return result
    
    def list_items(self, project_id: str = None, type_name: str = None,
                   status_name: str = None, tag_names: List[str] = None,
                   tag_match_mode: str = "any", limit: int = 50) -> List[Dict]:
        """List items with optional filters including tags.

        Args:
            project_id: Filter by project
            type_name: Filter by item type
            status_name: Filter by status
            tag_names: Filter by tags (list of tag names)
            tag_match_mode: 'any' (OR) or 'all' (AND) for tag filtering
            limit: Max items to return
        """
        # Normalize tag names for filtering (skip invalid ones)
        if tag_names:
            normalized_tags = []
            for name in tag_names:
                try:
                    normalized_tags.append(self._normalize_tag_name(name))
                except ValueError:
                    pass  # Skip empty or invalid tags in filter
            tag_names = normalized_tags if normalized_tags else None

        with self._db_cursor(dictionary=True) as cursor:
            # Base query
            query = """
                SELECT DISTINCT i.*, it.name as type_name, s.name as status_name, p.name as project_name
                FROM items i
                JOIN item_types it ON i.type_id = it.id
                JOIN statuses s ON i.status_id = s.id
                JOIN projects p ON i.project_id = p.id
            """
            params = []

            # Add tag filtering join if needed (for 'any' mode)
            if tag_names and tag_match_mode == "any":
                query += " JOIN item_tags itg ON i.id = itg.item_id JOIN tags t ON itg.tag_id = t.id"

            query += " WHERE 1=1"

            if project_id:
                query += " AND i.project_id = %s"
                params.append(project_id)
            if type_name:
                query += " AND it.name = %s"
                params.append(type_name)
            if status_name:
                query += " AND s.name = %s"
                params.append(status_name)

            # Tag filter
            if tag_names:
                if tag_match_mode == "any":
                    placeholders = ','.join(['%s'] * len(tag_names))
                    query += f" AND t.name IN ({placeholders})"
                    params.extend(tag_names)
                else:  # 'all' mode
                    placeholders = ','.join(['%s'] * len(tag_names))
                    query += f"""
                        AND i.id IN (
                            SELECT item_id
                            FROM item_tags itg2
                            JOIN tags t2 ON itg2.tag_id = t2.id
                            WHERE t2.name IN ({placeholders})
                            GROUP BY item_id
                            HAVING COUNT(DISTINCT t2.name) = %s
                        )
                    """
                    params.extend(tag_names)
                    params.append(len(tag_names))

            query += " ORDER BY i.priority ASC, i.created_at DESC LIMIT %s"
            params.append(limit)

            cursor.execute(query, params)
            return cursor.fetchall()

    def _record_status_change(self, item_id: int, old_status_id: Optional[int],
                              new_status_id: int, change_type: str) -> None:
        """Record a status change in status_history table."""
        with self._db_cursor(commit=True) as cursor:
            cursor.execute(
                """INSERT INTO status_history (item_id, old_status_id, new_status_id, change_type)
                   VALUES (%s, %s, %s, %s)""",
                (item_id, old_status_id, new_status_id, change_type)
            )

    def get_status_history(self, item_id: int) -> List[Dict]:
        """Get status history for an item, ordered chronologically (oldest first).

        Returns list of dicts with: id, item_id, old_status, new_status, change_type, changed_at
        """
        with self._db_cursor(dictionary=True) as cursor:
            cursor.execute("""
                SELECT sh.id, sh.item_id,
                       os.name as old_status, ns.name as new_status,
                       sh.change_type, sh.changed_at
                FROM status_history sh
                LEFT JOIN statuses os ON sh.old_status_id = os.id
                JOIN statuses ns ON sh.new_status_id = ns.id
                WHERE sh.item_id = %s
                ORDER BY sh.changed_at ASC, sh.id ASC
            """, (item_id,))
            return cursor.fetchall()

    def get_item_metrics(self, item_id: int) -> Optional[Dict]:
        """Calculate metrics for an item based on status history.

        Returns dict with:
            lead_time: Hours from creation to done/closed (None if not closed)
            cycle_time: Hours from first in_progress to done/closed (None if not done)
            time_in_each_status: Dict of {status_name: hours}
            revert_count: Number of revert operations
            current_age: Hours since creation (or until closure if closed)
        """
        item = self.get_item(item_id)
        if not item:
            return None

        history = self.get_status_history(item_id)
        if not history:
            return None

        created_at = item['created_at']
        closed_at = item.get('closed_at')
        now = datetime.now()

        # Find first time item reached done or closed from history
        first_done_at = None
        first_in_progress = None
        for entry in history:
            if entry['new_status'] in ('done', 'closed') and first_done_at is None:
                first_done_at = entry['changed_at']
            if entry['new_status'] == 'in_progress' and first_in_progress is None:
                first_in_progress = entry['changed_at']

        # Use closed_at if available, otherwise use first done timestamp from history
        completion_time = closed_at or first_done_at

        # Lead time: creation to done/closed
        lead_time = None
        if completion_time:
            lead_time = round((completion_time - created_at).total_seconds() / 3600, 2)

        # Cycle time: first in_progress to done/closed
        cycle_time = None
        if first_in_progress and completion_time:
            cycle_time = round((completion_time - first_in_progress).total_seconds() / 3600, 2)

        # Time in each status
        time_in_status = {}
        for i, entry in enumerate(history):
            status = entry['new_status']
            start_time = entry['changed_at']

            # End time is next transition or now
            if i + 1 < len(history):
                end_time = history[i + 1]['changed_at']
            else:
                end_time = completion_time if completion_time else now

            hours = (end_time - start_time).total_seconds() / 3600
            time_in_status[status] = round(time_in_status.get(status, 0) + hours, 2)

        # Revert count
        revert_count = sum(1 for entry in history if entry['change_type'] == 'revert')

        # Current age
        end_time = completion_time if completion_time else now
        current_age = round((end_time - created_at).total_seconds() / 3600, 2)

        return {
            'item_id': item_id,
            'complexity': item.get('complexity'),
            'lead_time': lead_time,
            'cycle_time': cycle_time,
            'time_in_each_status': time_in_status,
            'revert_count': revert_count,
            'current_age': current_age
        }

    def _check_blocking_constraint(self, item_id: int, target_status_name: str) -> Optional[Dict]:
        """Check if item can transition to target status.

        Args:
            item_id: Item to check
            target_status_name: Status attempting to transition to

        Returns:
            None if no blocking constraints
            Error dict with success=False, message, blockers if blocked
        """
        # Only check for completion statuses
        if target_status_name not in ('done', 'closed'):
            return None

        # Check relationship blockers
        blockers = self.get_blocking_items(item_id)
        if blockers:
            blocker_info = ", ".join([f"#{b['id']} ({b['reason']})" for b in blockers])
            return {
                "success": False,
                "message": f"Cannot transition to {target_status_name}: blocked by {blocker_info}",
                "blockers": blockers
            }

        # Check epic closure constraint (only for 'closed' status)
        if target_status_name == 'closed':
            epic_block = self._check_epic_closure(item_id)
            if epic_block:
                return epic_block

        return None

    def advance_status(self, item_id: int) -> Dict:
        """Move item to next status in workflow. Returns new status info."""
        item = self.get_item(item_id)
        if not item:
            raise ValueError(f"Item not found: {item_id}")

        # Get current and next status from workflow
        with self._db_cursor(dictionary=True) as cursor:
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

        # Check for blocking constraints
        if blocking_error := self._check_blocking_constraint(item_id, next_status["status_name"]):
            return blocking_error

        # Perform the update
        with self._db_cursor(commit=True) as cursor:
            cursor.execute(
                "UPDATE items SET status_id = %s WHERE id = %s",
                (next_status['status_id'], item_id)
            )

        # Record status change in history
        self._record_status_change(item_id, item['status_id'], next_status['status_id'], 'advance')

        # Auto-advance parent epics if this item is now complete
        if next_status['status_name'] in ('done', 'closed'):
            self._auto_advance_ancestors(item_id)

        return {
            "success": True,
            "previous_status": item['status_name'],
            "new_status": next_status['status_name']
        }

    def revert_status(self, item_id: int) -> Dict:
        """Move item to previous status in workflow. Returns new status info."""
        item = self.get_item(item_id)
        if not item:
            raise ValueError(f"Item not found: {item_id}")

        # Get current and previous status from workflow
        with self._db_cursor(dictionary=True) as cursor:
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

        # Perform the update
        with self._db_cursor(commit=True) as cursor:
            cursor.execute(
                "UPDATE items SET status_id = %s WHERE id = %s",
                (prev_status['status_id'], item_id)
            )

        # Record status change in history
        self._record_status_change(item_id, item['status_id'], prev_status['status_id'], 'revert')

        return {
            "success": True,
            "previous_status": item['status_name'],
            "new_status": prev_status['status_name']
        }

    def set_status(self, item_id: int, status_name: str) -> Dict:
        """Set item to specific status (must be valid for type)."""
        item = self.get_item(item_id)
        if not item:
            raise ValueError(f"Item not found: {item_id}")

        status_id = self.get_status_id(status_name)

        # Validate status is valid for this item type
        with self._db_cursor() as cursor:
            cursor.execute("""
                SELECT 1 FROM type_status_workflow
                WHERE type_id = %s AND status_id = %s
            """, (item['type_id'], status_id))
            if not cursor.fetchone():
                raise ValueError(f"Status '{status_name}' not valid for type '{item['type_name']}'")

        # Check for blocking constraints
        if blocking_error := self._check_blocking_constraint(item_id, status_name):
            return blocking_error

        # Perform the update
        with self._db_cursor(commit=True) as cursor:
            if status_name in ('done', 'closed'):
                cursor.execute(
                    "UPDATE items SET status_id = %s, closed_at = NOW() WHERE id = %s",
                    (status_id, item_id)
                )
            else:
                cursor.execute(
                    "UPDATE items SET status_id = %s, closed_at = NULL WHERE id = %s",
                    (status_id, item_id)
                )

        # Record status change in history
        self._record_status_change(item_id, item['status_id'], status_id, 'set')

        # Auto-advance parent epics if this item is now complete
        if status_name in ('done', 'closed'):
            self._auto_advance_ancestors(item_id)

        return {
            "success": True,
            "previous_status": item['status_name'],
            "new_status": status_name
        }

    def close_item(self, item_id: int) -> Dict:
        """Mark item as done/closed."""
        item = self.get_item(item_id)
        if not item:
            raise ValueError(f"Item not found: {item_id}")

        # Check for blocking constraints (close always targets final status)
        if blocking_error := self._check_blocking_constraint(item_id, "closed"):
            return blocking_error

        # Get final status and perform update
        with self._db_cursor(dictionary=True) as cursor:
            cursor.execute("""
                SELECT s.id, s.name
                FROM type_status_workflow tsw
                JOIN statuses s ON tsw.status_id = s.id
                WHERE tsw.type_id = %s
                ORDER BY tsw.sequence DESC LIMIT 1
            """, (item['type_id'],))
            final_status = cursor.fetchone()

        with self._db_cursor(commit=True) as cursor:
            cursor.execute(
                "UPDATE items SET status_id = %s, closed_at = NOW() WHERE id = %s",
                (final_status['id'], item_id)
            )

        # Record status change in history
        self._record_status_change(item_id, item['status_id'], final_status['id'], 'close')

        # Auto-advance parent epics if this item is now complete
        self._auto_advance_ancestors(item_id)

        return {
            "success": True,
            "previous_status": item['status_name'],
            "new_status": final_status['name']
        }

    def delete_item(self, item_id: int) -> Dict:
        """Delete an item."""
        # Delete embedding first (before item is deleted)
        self._safe_embedding_op('delete_embedding', 'item', item_id)

        with self._db_cursor(commit=True) as cursor:
            cursor.execute("DELETE FROM items WHERE id = %s", (item_id,))
            return {"success": True, "deleted_id": item_id, "rows_affected": cursor.rowcount}

    def update_item(self, item_id: int, title: str = None, description: str = None,
                    priority: int = None, complexity: int = None) -> Dict:
        """Update an existing item's title, description, priority, and/or complexity."""
        # Validate complexity if provided
        if complexity is not None and (complexity < 1 or complexity > 5):
            return {"success": False, "error": f"Complexity must be 1-5, got {complexity}"}

        # Check if item exists
        item = self.get_item(item_id)
        if not item:
            return {"success": False, "error": f"Item not found: {item_id}"}

        # Build update fields - only include fields that were explicitly passed
        updates = []
        params = []

        if title is not None:
            updates.append("title = %s")
            params.append(title)
        if description is not None:
            updates.append("description = %s")
            params.append(description)
        if priority is not None:
            updates.append("priority = %s")
            params.append(priority)
        if complexity is not None:
            updates.append("complexity = %s")
            params.append(complexity)

        if not updates:
            return {"success": False, "error": "No fields to update"}

        with self._db_cursor(commit=True) as cursor:
            query = f"UPDATE items SET {', '.join(updates)} WHERE id = %s"
            params.append(item_id)
            cursor.execute(query, params)

        # Re-embed if title or description changed
        if title is not None or description is not None:
            self._safe_embedding_op('upsert_embedding', 'item', item_id)

        updated_item = self.get_item(item_id)
        return {"success": True, "item": updated_item}

    def add_update(self, project_id: str, content: str, item_ids: List[int] = None) -> int:
        """Add an update, optionally linked to items. Returns update id."""
        with self._db_cursor(commit=True) as cursor:
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

        # Auto-generate embedding
        self._safe_embedding_op('upsert_embedding', 'update', update_id)

        return update_id

    def get_latest_update(self, project_id: str) -> Optional[Dict]:
        """Get most recent update for a project."""
        with self._db_cursor(dictionary=True) as cursor:
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
    
    def get_updates(self, project_id: str, limit: int = 20) -> List[Dict]:
        """Get recent updates for a project."""
        with self._db_cursor(dictionary=True) as cursor:
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

    def project_summary(self, project_id: str) -> Dict:
        """Get summary counts by type and status for a project."""
        with self._db_cursor(dictionary=True) as cursor:
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
    # --- Relationship Methods ---
    
    RELATIONSHIP_TYPES = ('blocks', 'depends_on', 'relates_to', 'duplicates')
    BLOCKING_STATUSES = ('done', 'closed')  # Items in these statuses don't block
    
    def add_relationship(self, source_id: int, target_id: int, relationship_type: str) -> Dict:
        """Add a relationship between two items."""
        if relationship_type not in self.RELATIONSHIP_TYPES:
            raise ValueError(f"Invalid relationship type: {relationship_type}. Must be one of {self.RELATIONSHIP_TYPES}")

        if source_id == target_id:
            raise ValueError("Cannot create relationship between an item and itself")

        # Verify both items exist and are in the same project
        source = self.get_item(source_id)
        target = self.get_item(target_id)
        if not source:
            raise ValueError(f"Source item not found: {source_id}")
        if not target:
            raise ValueError(f"Target item not found: {target_id}")
        if source['project_id'] != target['project_id']:
            raise ValueError("Cannot create relationship between items in different projects")

        try:
            with self._db_cursor(commit=True) as cursor:
                cursor.execute("""
                    INSERT INTO item_relationships (source_item_id, target_item_id, relationship_type)
                    VALUES (%s, %s, %s)
                """, (source_id, target_id, relationship_type))
                return {
                    "success": True,
                    "relationship_id": cursor.lastrowid,
                    "source_id": source_id,
                    "target_id": target_id,
                    "type": relationship_type
                }
        except Exception as e:
            if "Duplicate entry" in str(e):
                return {"success": False, "error": "Relationship already exists"}
            raise

    def remove_relationship(self, source_id: int, target_id: int, relationship_type: str) -> Dict:
        """Remove a relationship between two items."""
        with self._db_cursor(commit=True) as cursor:
            cursor.execute("""
                DELETE FROM item_relationships
                WHERE source_item_id = %s AND target_item_id = %s AND relationship_type = %s
            """, (source_id, target_id, relationship_type))
            return {
                "success": cursor.rowcount > 0,
                "rows_affected": cursor.rowcount
            }
    
    def get_item_relationships(self, item_id: int) -> Dict:
        """Get all relationships for an item (both directions)."""
        with self._db_cursor(dictionary=True) as cursor:
            # Relationships where this item is the source
            cursor.execute("""
                SELECT r.id, r.relationship_type, r.target_item_id as related_item_id,
                       i.title as related_item_title, s.name as related_item_status,
                       'outgoing' as direction
                FROM item_relationships r
                JOIN items i ON r.target_item_id = i.id
                JOIN statuses s ON i.status_id = s.id
                WHERE r.source_item_id = %s
            """, (item_id,))
            outgoing = cursor.fetchall()

            # Relationships where this item is the target
            cursor.execute("""
                SELECT r.id, r.relationship_type, r.source_item_id as related_item_id,
                       i.title as related_item_title, s.name as related_item_status,
                       'incoming' as direction
                FROM item_relationships r
                JOIN items i ON r.source_item_id = i.id
                JOIN statuses s ON i.status_id = s.id
                WHERE r.target_item_id = %s
            """, (item_id,))
            incoming = cursor.fetchall()

            return {
                "item_id": item_id,
                "outgoing": outgoing,  # This item blocks/depends_on/relates_to others
                "incoming": incoming   # Others block/depend_on/relate_to this item
            }

    def get_blocking_items(self, item_id: int) -> List[Dict]:
        """Get items that prevent this item from advancing to done/closed.

        Returns items that:
        - Block this item (relationship_type='blocks', target=this_item) AND are not done/closed
        - This item depends on (relationship_type='depends_on', source=this_item) AND are not done/closed
        """
        with self._db_cursor(dictionary=True) as cursor:
            cursor.execute("""
                SELECT DISTINCT i.id, i.title, s.name as status, 'blocks' as reason
                FROM item_relationships r
                JOIN items i ON r.source_item_id = i.id
                JOIN statuses s ON i.status_id = s.id
                WHERE r.target_item_id = %s
                  AND r.relationship_type = 'blocks'
                  AND s.name NOT IN ('done', 'closed')

                UNION

                SELECT DISTINCT i.id, i.title, s.name as status, 'dependency' as reason
                FROM item_relationships r
                JOIN items i ON r.target_item_id = i.id
                JOIN statuses s ON i.status_id = s.id
                WHERE r.source_item_id = %s
                  AND r.relationship_type = 'depends_on'
                  AND s.name NOT IN ('done', 'closed')
            """, (item_id, item_id))
            return cursor.fetchall()

    # --- Epic/Hierarchy Methods ---

    def get_all_descendants(self, item_id: int) -> List[Dict]:
        """Get all descendants of an item recursively using CTE.

        Returns list of dicts with: id, parent_id, status_name, depth
        Limited to depth 10 to prevent infinite loops.
        """
        with self._db_cursor(dictionary=True) as cursor:
            cursor.execute("""
                WITH RECURSIVE descendants AS (
                    SELECT i.id, i.parent_id, s.name as status_name, 0 as depth
                    FROM items i
                    JOIN statuses s ON i.status_id = s.id
                    WHERE i.parent_id = %s
                    UNION ALL
                    SELECT i.id, i.parent_id, s.name as status_name, d.depth + 1
                    FROM items i
                    JOIN statuses s ON i.status_id = s.id
                    JOIN descendants d ON i.parent_id = d.id
                    WHERE d.depth < 10
                )
                SELECT * FROM descendants
            """, (item_id,))
            return cursor.fetchall()

    def get_children(self, item_id: int) -> List[Dict]:
        """Get direct children of an item (not recursive)."""
        with self._db_cursor(dictionary=True) as cursor:
            cursor.execute("""
                SELECT i.*, it.name as type_name, s.name as status_name
                FROM items i
                JOIN item_types it ON i.type_id = it.id
                JOIN statuses s ON i.status_id = s.id
                WHERE i.parent_id = %s
                ORDER BY i.priority, i.id
            """, (item_id,))
            return cursor.fetchall()

    def get_epic_progress(self, item_id: int) -> Dict:
        """Calculate progress stats for an epic (or any parent item).

        Returns dict with:
            total: Total number of descendants
            completed: Number of descendants in 'done' or 'closed' status
            percent: Completion percentage (0-100)
            incomplete_items: List of incomplete descendant ids
        """
        descendants = self.get_all_descendants(item_id)

        total = len(descendants)
        completed = 0
        incomplete_items = []

        for d in descendants:
            if d['status_name'] in ('done', 'closed'):
                completed += 1
            else:
                incomplete_items.append(d['id'])

        percent = round((completed / total * 100) if total > 0 else 0, 1)

        return {
            'item_id': item_id,
            'total': total,
            'completed': completed,
            'percent': percent,
            'incomplete_items': incomplete_items
        }

    def set_parent(self, item_id: int, parent_id: int = None) -> Dict:
        """Set or remove parent relationship for an item.

        Args:
            item_id: Item to update
            parent_id: New parent ID, or None/0 to remove parent

        Returns:
            Dict with success status
        """
        item = self.get_item(item_id)
        if not item:
            return {"success": False, "error": f"Item not found: {item_id}"}

        # Convert 0 to None (for MCP tool compatibility)
        if parent_id == 0:
            parent_id = None

        if parent_id is not None:
            # Validate parent exists, is in same project, and is an epic
            parent = self.get_item(parent_id)
            if not parent:
                return {"success": False, "error": f"Parent item not found: {parent_id}"}
            if parent['project_id'] != item['project_id']:
                return {"success": False, "error": "Parent must be in the same project"}
            if parent['type_name'] != 'epic':
                return {"success": False, "error": "Parent must be an epic"}

            # Check for circular reference
            if self._would_create_cycle(item_id, parent_id):
                return {"success": False, "error": "Cannot set parent: would create circular reference"}

        with self._db_cursor(commit=True) as cursor:
            cursor.execute(
                "UPDATE items SET parent_id = %s WHERE id = %s",
                (parent_id, item_id)
            )

        return {"success": True, "item_id": item_id, "parent_id": parent_id}

    def _would_create_cycle(self, item_id: int, proposed_parent_id: int) -> bool:
        """Check if setting proposed_parent_id as parent of item_id would create a cycle."""
        # If proposed parent is the item itself
        if item_id == proposed_parent_id:
            return True

        # Check if item_id is an ancestor of proposed_parent_id
        # (i.e., proposed_parent_id is already a descendant of item_id)
        descendants = self.get_all_descendants(item_id)
        descendant_ids = {d['id'] for d in descendants}

        return proposed_parent_id in descendant_ids

    def _check_epic_closure(self, item_id: int) -> Optional[Dict]:
        """Check if an epic can be closed (all descendants must be complete).

        Returns None if closure is allowed, or error dict if blocked.
        """
        item = self.get_item(item_id)
        if not item:
            return None

        # Only check for epic items
        if item['type_name'] != 'epic':
            return None

        progress = self.get_epic_progress(item_id)
        if progress['incomplete_items']:
            incomplete_count = len(progress['incomplete_items'])
            return {
                "success": False,
                "message": f"Cannot close epic: {incomplete_count} incomplete child items",
                "incomplete_items": progress['incomplete_items']
            }

        return None

    def _auto_advance_ancestors(self, item_id: int) -> None:
        """Check parent epics and auto-advance to 'review' if all descendants complete.

        Called after status changes to propagate completion up the hierarchy.
        """
        item = self.get_item(item_id)
        if not item or not item.get('parent_id'):
            return

        parent = self.get_item(item['parent_id'])
        if not parent or parent['type_name'] != 'epic':
            return

        # Check if all descendants are complete
        progress = self.get_epic_progress(parent['id'])
        if progress['total'] > 0 and progress['completed'] == progress['total']:
            # Only auto-advance if not already in review or beyond
            if parent['status_name'] not in ('review', 'done', 'closed'):
                # Use internal method to avoid recursion through set_status
                old_status_id = parent['status_id']
                new_status_id = self.get_status_id('review')
                with self._db_cursor(commit=True) as cursor:
                    cursor.execute(
                        "UPDATE items SET status_id = %s WHERE id = %s",
                        (new_status_id, parent['id'])
                    )
                self._record_status_change(parent['id'], old_status_id, new_status_id, 'auto_advance')

                # Recurse to check grandparent
                self._auto_advance_ancestors(parent['id'])

    # --- Tag Methods ---

    def _normalize_tag_name(self, name: str) -> str:
        """Normalize and validate tag name.

        Args:
            name: Raw tag name from user input

        Returns:
            Normalized tag name (stripped, lowercase)

        Raises:
            ValueError: If tag name is empty or exceeds 50 characters
        """
        normalized = name.strip().lower()

        if not normalized:
            raise ValueError("Tag name cannot be empty")

        if len(normalized) > 50:
            raise ValueError(f"Tag name too long (max 50 chars, got {len(normalized)})")

        return normalized

    def _get_next_tag_color(self, project_id: str) -> str:
        """Get next color from palette using round-robin based on tag count."""
        with self._db_cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM tags WHERE project_id = %s",
                (project_id,)
            )
            result = cursor.fetchone()
            tag_count = result[0] if result else 0
            return self.TAG_COLOR_PALETTE[tag_count % len(self.TAG_COLOR_PALETTE)]

    def ensure_tag(self, project_id: str, name: str, color: str = None) -> int:
        """Get or create tag. Returns tag_id. Auto-assigns color if not provided."""
        name = self._normalize_tag_name(name)

        # Check if tag exists
        with self._db_cursor(dictionary=True) as cursor:
            cursor.execute(
                "SELECT id FROM tags WHERE project_id = %s AND name = %s",
                (project_id, name)
            )
            result = cursor.fetchone()
            if result:
                return result['id']

        # Create new tag with auto-color
        if color is None:
            color = self._get_next_tag_color(project_id)

        try:
            with self._db_cursor(commit=True) as cursor:
                cursor.execute(
                    "INSERT INTO tags (project_id, name, color) VALUES (%s, %s, %s)",
                    (project_id, name, color)
                )
                return cursor.lastrowid
        except Exception as e:
            if "Duplicate entry" in str(e):
                # Race condition: tag created by concurrent request
                with self._db_cursor(dictionary=True) as cursor:
                    cursor.execute(
                        "SELECT id FROM tags WHERE project_id = %s AND name = %s",
                        (project_id, name)
                    )
                    result = cursor.fetchone()
                    if result:
                        return result['id']
            raise

    def get_tag(self, tag_id: int) -> Optional[Dict]:
        """Get tag by ID."""
        with self._db_cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM tags WHERE id = %s", (tag_id,))
            return cursor.fetchone()

    def get_project_tags(self, project_id: str) -> List[Dict]:
        """Get all tags for a project with usage counts, ordered by name."""
        with self._db_cursor(dictionary=True) as cursor:
            cursor.execute("""
                SELECT t.*, COUNT(it.item_id) as count
                FROM tags t
                LEFT JOIN item_tags it ON t.id = it.tag_id
                WHERE t.project_id = %s
                GROUP BY t.id
                ORDER BY t.name
            """, (project_id,))
            return cursor.fetchall()

    def update_tag(self, tag_id: int, name: str = None, color: str = None) -> Dict:
        """Update tag name and/or color."""
        tag = self.get_tag(tag_id)
        if not tag:
            return {"success": False, "error": "Tag not found"}

        updates = []
        params = []

        if name is not None:
            try:
                name = self._normalize_tag_name(name)
                updates.append("name = %s")
                params.append(name)
            except ValueError as e:
                return {"success": False, "error": str(e)}

        if color is not None:
            # Strict hex color validation to prevent CSS injection
            import re
            if not re.match(r'^#[0-9a-fA-F]{6}$', color):
                return {"success": False, "error": "Invalid color format (use #RRGGBB hex)"}
            updates.append("color = %s")
            params.append(color)

        if not updates:
            return {"success": False, "error": "No fields to update"}

        try:
            with self._db_cursor(commit=True) as cursor:
                query = f"UPDATE tags SET {', '.join(updates)} WHERE id = %s"
                params.append(tag_id)
                cursor.execute(query, params)
            return {"success": True, "tag": self.get_tag(tag_id)}
        except Exception as e:
            if "Duplicate entry" in str(e):
                return {"success": False, "error": "Tag name already exists in this project"}
            raise

    def delete_tag(self, tag_id: int) -> Dict:
        """Delete tag and all item associations (cascades via FK)."""
        with self._db_cursor(commit=True) as cursor:
            cursor.execute("DELETE FROM tags WHERE id = %s", (tag_id,))
            return {
                "success": cursor.rowcount > 0,
                "deleted_id": tag_id,
                "rows_affected": cursor.rowcount
            }

    def add_tag_to_item(self, item_id: int, tag_name: str) -> Dict:
        """Add a tag to an item (creates tag on-the-fly if needed)."""
        item = self.get_item(item_id)
        if not item:
            raise ValueError(f"Item not found: {item_id}")

        # ensure_tag handles normalization
        tag_id = self.ensure_tag(item['project_id'], tag_name)
        normalized_name = self._normalize_tag_name(tag_name)

        try:
            with self._db_cursor(commit=True) as cursor:
                cursor.execute(
                    "INSERT INTO item_tags (item_id, tag_id) VALUES (%s, %s)",
                    (item_id, tag_id)
                )
            return {
                "success": True,
                "item_id": item_id,
                "tag_id": tag_id,
                "tag_name": normalized_name
            }
        except Exception as e:
            if "Duplicate entry" in str(e):
                return {"success": False, "error": "Tag already assigned to item"}
            raise

    def remove_tag_from_item(self, item_id: int, tag_id: int) -> Dict:
        """Remove a tag from an item."""
        with self._db_cursor(commit=True) as cursor:
            cursor.execute(
                "DELETE FROM item_tags WHERE item_id = %s AND tag_id = %s",
                (item_id, tag_id)
            )
            return {
                "success": cursor.rowcount > 0,
                "rows_affected": cursor.rowcount
            }

    def get_item_tags(self, item_id: int) -> List[Dict]:
        """Get all tags for an item."""
        with self._db_cursor(dictionary=True) as cursor:
            cursor.execute("""
                SELECT t.id, t.name, t.color
                FROM tags t
                JOIN item_tags it ON t.id = it.tag_id
                WHERE it.item_id = %s
                ORDER BY t.name
            """, (item_id,))
            return cursor.fetchall()

    # --- Search Methods ---

    def search(self, project_id: str, query: str, limit: int = 20) -> Dict[str, Any]:
        """Full-text search across items and updates.

        Args:
            project_id: Project to search within
            query: Search query string (use * for wildcard prefix matching)
            limit: Maximum results per category (default 20)

        Returns:
            Dict with 'items', 'updates', and 'total_count' keys.
            Items include: id, title, snippet, score, type_name, status_name
            Updates include: id, snippet, score, created_at
        """
        items = []
        updates = []

        # Use BOOLEAN MODE if query contains wildcard, otherwise NATURAL LANGUAGE
        use_boolean = '*' in query
        mode = 'IN BOOLEAN MODE' if use_boolean else 'IN NATURAL LANGUAGE MODE'

        with self._db_cursor(dictionary=True) as cursor:
            # Search items (title and description)
            cursor.execute(f"""
                SELECT i.id, i.title, i.description,
                       it.name as type_name, s.name as status_name,
                       MATCH(i.title, i.description) AGAINST(%s {mode}) as score
                FROM items i
                JOIN item_types it ON i.type_id = it.id
                JOIN statuses s ON i.status_id = s.id
                WHERE i.project_id = %s
                  AND MATCH(i.title, i.description) AGAINST(%s {mode})
                ORDER BY score DESC
                LIMIT %s
            """, (query, project_id, query, limit))

            for row in cursor.fetchall():
                # Create snippet from title or description
                snippet = row['title']
                if row['description']:
                    snippet = row['description'][:100] + ('...' if len(row['description']) > 100 else '')

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
            """, (query, project_id, query, limit))

            for row in cursor.fetchall():
                snippet = row['content'][:100] + ('...' if len(row['content']) > 100 else '')
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

    # --- File Linking Methods ---

    def link_file(self, item_id: int, file_path: str, line_start: int = None, line_end: int = None) -> Dict[str, Any]:
        """Link a file (or file region) to an item.

        Args:
            item_id: The item to link the file to
            file_path: Relative path to the file
            line_start: Optional starting line number
            line_end: Optional ending line number

        Returns:
            Dict with success status and link_id if successful

        Raises:
            ValueError: If item doesn't exist
        """
        with self._db_cursor(dictionary=True, commit=True) as cursor:
            # Verify item exists
            cursor.execute("SELECT id FROM items WHERE id = %s", (item_id,))
            if not cursor.fetchone():
                raise ValueError(f"Item {item_id} not found")

            # Check for duplicate link
            cursor.execute("""
                SELECT id FROM item_files
                WHERE item_id = %s AND file_path = %s
                  AND (line_start IS NULL AND %s IS NULL OR line_start = %s)
                  AND (line_end IS NULL AND %s IS NULL OR line_end = %s)
            """, (item_id, file_path, line_start, line_start, line_end, line_end))

            if cursor.fetchone():
                return {'success': False, 'error': 'Link already exists for this file and line range'}

            # Insert new link
            cursor.execute("""
                INSERT INTO item_files (item_id, file_path, line_start, line_end)
                VALUES (%s, %s, %s, %s)
            """, (item_id, file_path, line_start, line_end))

            link_id = cursor.lastrowid
            return {'success': True, 'link_id': link_id}

    def unlink_file(self, item_id: int, file_path: str, line_start: int = None, line_end: int = None) -> Dict[str, Any]:
        """Remove a file link from an item.

        Args:
            item_id: The item to unlink the file from
            file_path: Relative path to the file
            line_start: Optional starting line number (must match to unlink)
            line_end: Optional ending line number (must match to unlink)

        Returns:
            Dict with success status
        """
        with self._db_cursor(commit=True) as cursor:
            cursor.execute("""
                DELETE FROM item_files
                WHERE item_id = %s AND file_path = %s
                  AND (line_start IS NULL AND %s IS NULL OR line_start = %s)
                  AND (line_end IS NULL AND %s IS NULL OR line_end = %s)
            """, (item_id, file_path, line_start, line_start, line_end, line_end))

            if cursor.rowcount > 0:
                return {'success': True}
            return {'success': False, 'error': 'Link not found'}

    def get_item_files(self, item_id: int) -> List[Dict]:
        """Get all files linked to an item.

        Args:
            item_id: The item ID to get files for

        Returns:
            List of dicts with file_path, line_start, line_end, created_at
        """
        with self._db_cursor(dictionary=True) as cursor:
            cursor.execute("""
                SELECT id, file_path, line_start, line_end, created_at
                FROM item_files
                WHERE item_id = %s
                ORDER BY file_path, line_start
            """, (item_id,))
            return cursor.fetchall()

    # --- Decision History Methods ---

    def add_decision(self, item_id: int, choice: str, rejected_alternatives: str = None,
                     rationale: str = None) -> Dict[str, Any]:
        """Add a decision record to an item.

        Args:
            item_id: The item to attach the decision to
            choice: What was decided (max 200 chars, required)
            rejected_alternatives: What was rejected (max 500 chars, optional)
            rationale: Brief reason for the choice (max 200 chars, optional)

        Returns:
            Dict with success status and decision_id if successful

        Raises:
            ValueError: If item doesn't exist or choice exceeds max length
        """
        # Validate choice length
        if len(choice) > 200:
            raise ValueError(f"Choice exceeds 200 char limit (got {len(choice)})")

        # Validate rejected_alternatives length
        if rejected_alternatives and len(rejected_alternatives) > 500:
            raise ValueError(f"Rejected alternatives exceeds 500 char limit (got {len(rejected_alternatives)})")

        # Validate rationale length
        if rationale and len(rationale) > 200:
            raise ValueError(f"Rationale exceeds 200 char limit (got {len(rationale)})")

        with self._db_cursor(dictionary=True, commit=True) as cursor:
            # Verify item exists
            cursor.execute("SELECT id FROM items WHERE id = %s", (item_id,))
            if not cursor.fetchone():
                raise ValueError(f"Item {item_id} not found")

            # Insert decision
            cursor.execute("""
                INSERT INTO item_decisions (item_id, choice, rejected_alternatives, rationale)
                VALUES (%s, %s, %s, %s)
            """, (item_id, choice, rejected_alternatives, rationale))

            decision_id = cursor.lastrowid

        # Auto-generate embedding
        self._safe_embedding_op('upsert_embedding', 'decision', decision_id)

        return {'success': True, 'decision_id': decision_id}

    def get_item_decisions(self, item_id: int) -> List[Dict]:
        """Get all decisions for an item, ordered by created_at DESC.

        Args:
            item_id: The item ID to get decisions for

        Returns:
            List of dicts with id, choice, rejected_alternatives, rationale, created_at
        """
        with self._db_cursor(dictionary=True) as cursor:
            cursor.execute("""
                SELECT id, item_id, choice, rejected_alternatives, rationale, created_at
                FROM item_decisions
                WHERE item_id = %s
                ORDER BY created_at DESC, id DESC
            """, (item_id,))
            return cursor.fetchall()

    def delete_decision(self, decision_id: int) -> Dict[str, Any]:
        """Delete a decision record.

        Args:
            decision_id: The decision ID to delete

        Returns:
            Dict with success status
        """
        # Delete embedding first
        self._safe_embedding_op('delete_embedding', 'decision', decision_id)

        with self._db_cursor(commit=True) as cursor:
            cursor.execute("DELETE FROM item_decisions WHERE id = %s", (decision_id,))
            if cursor.rowcount > 0:
                return {'success': True, 'deleted_id': decision_id}
            return {'success': False, 'error': 'Decision not found'}

    # --- Embedding Methods ---

    EMBEDDING_MODEL = 'nomic-embed-text-v1.5'
    EMBEDDING_DIM = 768
    VALID_SOURCE_TYPES = ('item', 'decision', 'update')

    def _init_embedding_model(self):
        """Initialize ONNX embedding model (lazy load)."""
        global _onnx_session, _tokenizer

        if _onnx_session is not None:
            return

        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer
            from huggingface_hub import hf_hub_download

            # Try to find model in models/ directory
            model_dir = Path(__file__).parent / 'models' / 'nomic-embed-text-v1.5'

            if not model_dir.exists():
                # Download from HuggingFace
                model_path = hf_hub_download(
                    repo_id="nomic-ai/nomic-embed-text-v1.5",
                    filename="onnx/model.onnx"
                )
                tokenizer_path = hf_hub_download(
                    repo_id="nomic-ai/nomic-embed-text-v1.5",
                    filename="tokenizer.json"
                )
            else:
                model_path = model_dir / 'onnx' / 'model.onnx'
                tokenizer_path = model_dir / 'tokenizer.json'

            _tokenizer = Tokenizer.from_file(str(tokenizer_path))
            _tokenizer.enable_truncation(max_length=8192)
            _tokenizer.enable_padding()

            _onnx_session = ort.InferenceSession(
                str(model_path),
                providers=['CPUExecutionProvider']
            )
        except Exception as e:
            raise RuntimeError(f"Failed to load embedding model: {e}")

    def generate_embedding(self, text: str) -> bytes:
        """Generate embedding for text, return as packed bytes.

        Args:
            text: Text to embed

        Returns:
            bytes: Packed float32 array (768 * 4 = 3072 bytes)
        """
        self._init_embedding_model()

        # Tokenize with nomic prefix for search documents
        # nomic-embed uses "search_document: " prefix for documents
        prefixed_text = f"search_document: {text}"

        encoded = _tokenizer.encode(prefixed_text)

        # Build numpy arrays for ONNX - add batch dimension
        input_ids = np.array([encoded.ids], dtype=np.int64)
        attention_mask = np.array([encoded.attention_mask], dtype=np.int64)

        # Build input dict
        input_dict = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
        }

        # Add token_type_ids if model requires it
        input_names = [inp.name for inp in _onnx_session.get_inputs()]
        if "token_type_ids" in input_names:
            input_dict["token_type_ids"] = np.zeros_like(input_ids, dtype=np.int64)

        # Run inference
        outputs = _onnx_session.run(None, input_dict)

        # Get embeddings - model outputs [batch, seq_len, hidden] or [batch, hidden]
        embeddings = outputs[0]

        # Mean pooling over sequence dimension if needed
        if len(embeddings.shape) == 3:
            mask_expanded = np.expand_dims(attention_mask, -1)
            sum_embeddings = np.sum(embeddings * mask_expanded, axis=1)
            sum_mask = np.clip(np.sum(mask_expanded, axis=1), a_min=1e-9, a_max=None)
            embeddings = sum_embeddings / sum_mask

        # Normalize to unit vector
        embeddings = embeddings / np.linalg.norm(embeddings, axis=-1, keepdims=True)

        # Pack as bytes
        return embeddings[0].astype(np.float32).tobytes()

    def _get_content_for_embedding(self, source_type: str, source_id: int) -> Optional[str]:
        """Build text to embed based on source type.

        Args:
            source_type: 'item', 'decision', or 'update'
            source_id: ID of the source record

        Returns:
            Text to embed, or None if source not found
        """
        if source_type == 'item':
            item = self.get_item(source_id)
            if not item:
                return None
            parts = [item['title']]
            if item.get('description'):
                parts.append(item['description'])
            return ' '.join(parts)

        elif source_type == 'decision':
            with self._db_cursor(dictionary=True) as cursor:
                cursor.execute(
                    "SELECT choice, rejected_alternatives, rationale FROM item_decisions WHERE id = %s",
                    (source_id,)
                )
                decision = cursor.fetchone()
                if not decision:
                    return None
                parts = [decision['choice']]
                if decision.get('rejected_alternatives'):
                    parts.append(f"Rejected: {decision['rejected_alternatives']}")
                if decision.get('rationale'):
                    parts.append(f"Rationale: {decision['rationale']}")
                return ' '.join(parts)

        elif source_type == 'update':
            with self._db_cursor(dictionary=True) as cursor:
                cursor.execute("SELECT content FROM updates WHERE id = %s", (source_id,))
                update = cursor.fetchone()
                if not update:
                    return None
                return update['content']

        return None

    def _compute_content_hash(self, content: str) -> str:
        """Compute MD5 hash of content for change detection."""
        return hashlib.md5(content.encode()).hexdigest()

    def upsert_embedding(self, source_type: str, source_id: int) -> Dict[str, Any]:
        """Generate and store embedding for a source.

        Args:
            source_type: 'item', 'decision', or 'update'
            source_id: ID of the source record

        Returns:
            Dict with success, status ('created', 'updated', 'unchanged'), embedding_id
        """
        if source_type not in self.VALID_SOURCE_TYPES:
            return {'success': False, 'error': f'Invalid source type: {source_type}'}

        # Get content to embed
        content = self._get_content_for_embedding(source_type, source_id)
        if content is None:
            return {'success': False, 'error': f'{source_type} not found: {source_id}'}

        content_hash = self._compute_content_hash(content)

        # Check if embedding exists and is current
        with self._db_cursor(dictionary=True) as cursor:
            cursor.execute("""
                SELECT id, content_hash FROM embeddings
                WHERE source_type = %s AND source_id = %s AND model = %s
            """, (source_type, source_id, self.EMBEDDING_MODEL))
            existing = cursor.fetchone()

        if existing and existing['content_hash'] == content_hash:
            return {'success': True, 'status': 'unchanged', 'embedding_id': existing['id']}

        # Generate new embedding
        try:
            vector = self.generate_embedding(content)
        except Exception as e:
            return {'success': False, 'error': f'Embedding generation failed: {e}'}

        # Upsert into database
        with self._db_cursor(commit=True) as cursor:
            if existing:
                cursor.execute("""
                    UPDATE embeddings SET vector = %s, content_hash = %s, created_at = NOW()
                    WHERE id = %s
                """, (vector, content_hash, existing['id']))
                return {'success': True, 'status': 'updated', 'embedding_id': existing['id']}
            else:
                cursor.execute("""
                    INSERT INTO embeddings (source_type, source_id, content_hash, model, vector)
                    VALUES (%s, %s, %s, %s, %s)
                """, (source_type, source_id, content_hash, self.EMBEDDING_MODEL, vector))
                return {'success': True, 'status': 'created', 'embedding_id': cursor.lastrowid}

    def get_embedding(self, source_type: str, source_id: int) -> Optional[Dict]:
        """Retrieve embedding for a source.

        Args:
            source_type: 'item', 'decision', or 'update'
            source_id: ID of the source record

        Returns:
            Dict with id, source_type, source_id, content_hash, model, vector, created_at
            or None if not found
        """
        with self._db_cursor(dictionary=True) as cursor:
            cursor.execute("""
                SELECT id, source_type, source_id, content_hash, model, vector, created_at
                FROM embeddings
                WHERE source_type = %s AND source_id = %s AND model = %s
            """, (source_type, source_id, self.EMBEDDING_MODEL))
            return cursor.fetchone()

    def delete_embedding(self, source_type: str, source_id: int) -> Dict[str, Any]:
        """Remove embedding when source is deleted.

        Args:
            source_type: 'item', 'decision', or 'update'
            source_id: ID of the source record

        Returns:
            Dict with success status
        """
        with self._db_cursor(commit=True) as cursor:
            cursor.execute("""
                DELETE FROM embeddings
                WHERE source_type = %s AND source_id = %s AND model = %s
            """, (source_type, source_id, self.EMBEDDING_MODEL))
            if cursor.rowcount > 0:
                return {'success': True}
            return {'success': False, 'error': 'Embedding not found'}

    def semantic_search(self, project_id: str, query: str, limit: int = 10,
                        source_types: List[str] = None, threshold: float = 0.0) -> List[Dict]:
        """Search by semantic similarity.

        Args:
            project_id: Project to search within
            query: Search query text
            limit: Maximum results to return
            source_types: Filter by source types (default: all)
            threshold: Minimum similarity score (0.0 to 1.0)

        Returns:
            List of dicts with source_type, source_id, similarity, title/content
        """
        # Generate query embedding with search prefix
        self._init_embedding_model()

        # nomic-embed uses "search_query: " prefix for queries
        prefixed_query = f"search_query: {query}"
        encoded = _tokenizer.encode(prefixed_query)

        # Build numpy arrays for ONNX
        input_ids = np.array([encoded.ids], dtype=np.int64)
        attention_mask = np.array([encoded.attention_mask], dtype=np.int64)

        input_dict = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
        }
        input_names = [inp.name for inp in _onnx_session.get_inputs()]
        if "token_type_ids" in input_names:
            input_dict["token_type_ids"] = np.zeros_like(input_ids, dtype=np.int64)

        outputs = _onnx_session.run(None, input_dict)

        embeddings = outputs[0]
        if len(embeddings.shape) == 3:
            mask_expanded = np.expand_dims(attention_mask, -1)
            sum_embeddings = np.sum(embeddings * mask_expanded, axis=1)
            sum_mask = np.clip(np.sum(mask_expanded, axis=1), a_min=1e-9, a_max=None)
            embeddings = sum_embeddings / sum_mask

        embeddings = embeddings / np.linalg.norm(embeddings, axis=-1, keepdims=True)
        query_vector = embeddings[0].astype(np.float32)

        # Build source type filter
        if source_types:
            type_filter = source_types
        else:
            type_filter = list(self.VALID_SOURCE_TYPES)

        # Get all embeddings for this project's items
        # We need to join with items/decisions/updates to filter by project
        results = []

        with self._db_cursor(dictionary=True) as cursor:
            for source_type in type_filter:
                if source_type == 'item':
                    cursor.execute("""
                        SELECT e.id, e.source_type, e.source_id, e.vector,
                               i.title, i.description, it.name as type_name, s.name as status_name
                        FROM embeddings e
                        JOIN items i ON e.source_id = i.id
                        JOIN item_types it ON i.type_id = it.id
                        JOIN statuses s ON i.status_id = s.id
                        WHERE e.source_type = 'item' AND e.model = %s AND i.project_id = %s
                    """, (self.EMBEDDING_MODEL, project_id))

                    for row in cursor.fetchall():
                        stored_vector = np.frombuffer(row['vector'], dtype=np.float32)
                        similarity = float(np.dot(query_vector, stored_vector))
                        if similarity >= threshold:
                            results.append({
                                'source_type': 'item',
                                'source_id': row['source_id'],
                                'similarity': round(similarity, 4),
                                'title': row['title'],
                                'snippet': row['description'][:100] if row['description'] else None,
                                'type_name': row['type_name'],
                                'status_name': row['status_name']
                            })

                elif source_type == 'decision':
                    cursor.execute("""
                        SELECT e.id, e.source_type, e.source_id, e.vector,
                               d.choice, d.item_id
                        FROM embeddings e
                        JOIN item_decisions d ON e.source_id = d.id
                        JOIN items i ON d.item_id = i.id
                        WHERE e.source_type = 'decision' AND e.model = %s AND i.project_id = %s
                    """, (self.EMBEDDING_MODEL, project_id))

                    for row in cursor.fetchall():
                        stored_vector = np.frombuffer(row['vector'], dtype=np.float32)
                        similarity = float(np.dot(query_vector, stored_vector))
                        if similarity >= threshold:
                            results.append({
                                'source_type': 'decision',
                                'source_id': row['source_id'],
                                'similarity': round(similarity, 4),
                                'title': row['choice'],
                                'item_id': row['item_id']
                            })

                elif source_type == 'update':
                    cursor.execute("""
                        SELECT e.id, e.source_type, e.source_id, e.vector,
                               u.content, u.created_at
                        FROM embeddings e
                        JOIN updates u ON e.source_id = u.id
                        WHERE e.source_type = 'update' AND e.model = %s AND u.project_id = %s
                    """, (self.EMBEDDING_MODEL, project_id))

                    for row in cursor.fetchall():
                        stored_vector = np.frombuffer(row['vector'], dtype=np.float32)
                        similarity = float(np.dot(query_vector, stored_vector))
                        if similarity >= threshold:
                            results.append({
                                'source_type': 'update',
                                'source_id': row['source_id'],
                                'similarity': round(similarity, 4),
                                'snippet': row['content'][:100] if row['content'] else None,
                                'created_at': row['created_at']
                            })

        # Sort by similarity descending and limit
        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results[:limit]

    def find_similar(self, source_type: str, source_id: int, limit: int = 5,
                     threshold: float = 0.0) -> List[Dict]:
        """Find items similar to a given source.

        Args:
            source_type: Type of source to find similar to
            source_id: ID of source to find similar to
            limit: Maximum results
            threshold: Minimum similarity

        Returns:
            List of similar items (excluding the source itself)
        """
        # Get the source embedding
        embedding = self.get_embedding(source_type, source_id)
        if not embedding:
            return []

        source_vector = np.frombuffer(embedding['vector'], dtype=np.float32)

        # Get project_id from the source
        project_id = None
        if source_type == 'item':
            item = self.get_item(source_id)
            if item:
                project_id = item['project_id']
        elif source_type == 'decision':
            with self._db_cursor(dictionary=True) as cursor:
                cursor.execute("""
                    SELECT i.project_id FROM item_decisions d
                    JOIN items i ON d.item_id = i.id
                    WHERE d.id = %s
                """, (source_id,))
                row = cursor.fetchone()
                if row:
                    project_id = row['project_id']
        elif source_type == 'update':
            with self._db_cursor(dictionary=True) as cursor:
                cursor.execute("SELECT project_id FROM updates WHERE id = %s", (source_id,))
                row = cursor.fetchone()
                if row:
                    project_id = row['project_id']

        if not project_id:
            return []

        # Get all embeddings for comparison
        results = []
        with self._db_cursor(dictionary=True) as cursor:
            # Items
            cursor.execute("""
                SELECT e.source_type, e.source_id, e.vector, i.title
                FROM embeddings e
                JOIN items i ON e.source_id = i.id AND e.source_type = 'item'
                WHERE e.model = %s AND i.project_id = %s
            """, (self.EMBEDDING_MODEL, project_id))

            for row in cursor.fetchall():
                # Skip self
                if row['source_type'] == source_type and row['source_id'] == source_id:
                    continue
                stored_vector = np.frombuffer(row['vector'], dtype=np.float32)
                similarity = float(np.dot(source_vector, stored_vector))
                if similarity >= threshold:
                    results.append({
                        'source_type': row['source_type'],
                        'source_id': row['source_id'],
                        'similarity': round(similarity, 4),
                        'title': row['title']
                    })

            # Decisions
            cursor.execute("""
                SELECT e.source_type, e.source_id, e.vector, d.choice
                FROM embeddings e
                JOIN item_decisions d ON e.source_id = d.id AND e.source_type = 'decision'
                JOIN items i ON d.item_id = i.id
                WHERE e.model = %s AND i.project_id = %s
            """, (self.EMBEDDING_MODEL, project_id))

            for row in cursor.fetchall():
                if row['source_type'] == source_type and row['source_id'] == source_id:
                    continue
                stored_vector = np.frombuffer(row['vector'], dtype=np.float32)
                similarity = float(np.dot(source_vector, stored_vector))
                if similarity >= threshold:
                    results.append({
                        'source_type': row['source_type'],
                        'source_id': row['source_id'],
                        'similarity': round(similarity, 4),
                        'title': row['choice']
                    })

            # Updates
            cursor.execute("""
                SELECT e.source_type, e.source_id, e.vector, u.content
                FROM embeddings e
                JOIN updates u ON e.source_id = u.id AND e.source_type = 'update'
                WHERE e.model = %s AND u.project_id = %s
            """, (self.EMBEDDING_MODEL, project_id))

            for row in cursor.fetchall():
                if row['source_type'] == source_type and row['source_id'] == source_id:
                    continue
                stored_vector = np.frombuffer(row['vector'], dtype=np.float32)
                similarity = float(np.dot(source_vector, stored_vector))
                if similarity >= threshold:
                    results.append({
                        'source_type': row['source_type'],
                        'source_id': row['source_id'],
                        'similarity': round(similarity, 4),
                        'snippet': row['content'][:100] if row['content'] else None
                    })

        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results[:limit]

    def _rebuild_source_type(self, source_type: str, query: str, params: tuple = ()) -> tuple:
        """Fetch IDs, close cursor, then rebuild embeddings for each.

        Returns:
            Tuple of (processed_count, error_list)
        """
        with self._db_cursor(dictionary=True) as cursor:
            cursor.execute(query, params)
            ids = [row['id'] for row in cursor.fetchall()]
        # Cursor/connection released before processing
        processed, errors = 0, []
        for source_id in ids:
            result = self.upsert_embedding(source_type, source_id)
            if result['success']:
                processed += 1
            else:
                errors.append(f"{source_type}:{source_id}: {result.get('error')}")
        return processed, errors

    def rebuild_embeddings(self, project_id: str, source_types: List[str] = None) -> Dict[str, Any]:
        """Rebuild all embeddings for a project.

        Args:
            project_id: Project to rebuild embeddings for
            source_types: Types to rebuild (default: all)

        Returns:
            Dict with success, processed count, errors
        """
        if source_types is None:
            source_types = list(self.VALID_SOURCE_TYPES)

        processed = 0
        errors = []

        if 'item' in source_types:
            p, e = self._rebuild_source_type(
                'item', "SELECT id FROM items WHERE project_id = %s", (project_id,))
            processed += p
            errors.extend(e)

        if 'decision' in source_types:
            p, e = self._rebuild_source_type(
                'decision',
                "SELECT d.id FROM item_decisions d JOIN items i ON d.item_id = i.id WHERE i.project_id = %s",
                (project_id,))
            processed += p
            errors.extend(e)

        if 'update' in source_types:
            p, e = self._rebuild_source_type(
                'update', "SELECT id FROM updates WHERE project_id = %s", (project_id,))
            processed += p
            errors.extend(e)

        return {
            'success': True,
            'processed': processed,
            'errors': errors if errors else None
        }

    def rebuild_all_embeddings(self, source_types: List[str] = None) -> Dict[str, Any]:
        """Rebuild embeddings for ALL projects.

        Args:
            source_types: Types to rebuild (default: all)

        Returns:
            Dict with success, processed count, errors, project_count
        """
        if source_types is None:
            source_types = list(self.VALID_SOURCE_TYPES)

        processed = 0
        errors = []

        if 'item' in source_types:
            p, e = self._rebuild_source_type('item', "SELECT id FROM items")
            processed += p
            errors.extend(e)

        if 'decision' in source_types:
            p, e = self._rebuild_source_type('decision', "SELECT id FROM item_decisions")
            processed += p
            errors.extend(e)

        if 'update' in source_types:
            p, e = self._rebuild_source_type('update', "SELECT id FROM updates")
            processed += p
            errors.extend(e)

        return {
            'success': True,
            'processed': processed,
            'errors': errors if errors else None
        }

    # --- Timeline Methods ---

    def get_timeline_data(self, item_id: int = None, project_id: str = None,
                          limit: int = 100, repo_path: str = None) -> Dict[str, Any]:
        """Get unified activity timeline for an item or project.

        Aggregates status changes, decisions, updates, and git commits.

        Args:
            item_id: Get timeline for specific item (optional)
            project_id: Get timeline for entire project (optional)
            limit: Maximum entries to return
            repo_path: Path to git repo for commit history (optional)

        Returns:
            Dict with success, entries list, and entry_count
        """
        from kanban_mcp.timeline_builder import TimelineBuilder
        from kanban_mcp.git_timeline import GitTimelineProvider

        # Initialize git provider if repo path provided
        git_provider = None
        if repo_path:
            git_provider = GitTimelineProvider(repo_path)
            if not git_provider.is_valid():
                git_provider = None

        # Build timeline
        builder = TimelineBuilder(self, git_provider)

        if item_id:
            entries = builder.build_item_timeline(item_id, limit=limit)
        elif project_id:
            entries = builder.build_project_timeline(project_id, limit=limit)
        else:
            return {'success': False, 'error': 'Either item_id or project_id required'}

        # Serialize for JSON output
        serialized = builder.serialize_timeline(entries)

        return {
            'success': True,
            'entries': serialized,
            'entry_count': len(serialized)
        }


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

        # Silence noisy MySQL connector logging
        logging.getLogger('mysql.connector').setLevel(logging.WARNING)
        
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
                     description: str = "", priority: int = 3,
                     complexity: int = 0, parent_id: int = 0) -> Dict[str, Any]:
            """Create a new issue, todo, feature, epic, or diary entry for current project."""
            project_id = self._get_project_id()
            item_id = self.db.create_item(
                project_id=project_id,
                type_name=item_type,
                title=title,
                description=description if description else None,
                priority=priority,
                complexity=complexity if complexity else None,
                parent_id=parent_id if parent_id else None
            )
            item = self.db.get_item(item_id)
            return {"success": True, "item": self._serialize_result(item)}
        
        @self.tool("list_items")
        def list_items(item_type: str = "", status: str = "",
                       tags: str = "", tag_mode: str = "any",
                       limit: int = 50) -> Dict[str, Any]:
            """List items for current project with optional type/status/tag filters."""
            project_id = self._get_project_id()
            tag_list = [t.strip() for t in tags.split(',') if t.strip()] if tags else None
            items = self.db.list_items(
                project_id=project_id,
                type_name=item_type if item_type else None,
                status_name=status if status else None,
                tag_names=tag_list,
                tag_match_mode=tag_mode,
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

        @self.tool("edit_item")
        def edit_item(item_id: int, title: str = "", description: str = "",
                      priority: int = 0, complexity: int = 0, parent_id: int = -1) -> Dict[str, Any]:
            """Edit an existing item's title, description, priority, complexity, and/or parent.

            Note: Empty string/zero means 'don't update this field'. To clear description,
            use a single space. Complexity 0 means 'don't update'. Parent -1 means 'don't update',
            0 means 'remove parent'.
            """
            # Convert empty/zero to None (MCP passes defaults for unset params)
            # Non-empty values are passed through for update
            result = self.db.update_item(
                item_id,
                title=title if title else None,
                description=description if description else None,
                priority=priority if priority else None,
                complexity=complexity if complexity else None
            )

            # Handle parent_id change separately
            if parent_id != -1 and result.get('success', True):
                parent_result = self.db.set_parent(item_id, parent_id if parent_id else None)
                if not parent_result.get('success'):
                    return self._serialize_result(parent_result)
                # Refresh item data
                result = {"success": True, "item": self.db.get_item(item_id)}

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
        
        # --- Relationship Tools ---
        
        @self.tool("add_relationship")
        def add_relationship(source_id: int, target_id: int, relationship_type: str) -> Dict[str, Any]:
            """Add a relationship between two items.
            
            Types: 'blocks' (source blocks target from completing),
                   'depends_on' (source depends on target being complete),
                   'relates_to' (informational),
                   'duplicates' (informational)
            """
            return self.db.add_relationship(source_id, target_id, relationship_type)
        
        @self.tool("remove_relationship")
        def remove_relationship(source_id: int, target_id: int, relationship_type: str) -> Dict[str, Any]:
            """Remove a relationship between two items."""
            return self.db.remove_relationship(source_id, target_id, relationship_type)
        
        @self.tool("get_item_relationships")
        def get_item_relationships(item_id: int) -> Dict[str, Any]:
            """Get all relationships for an item (both directions)."""
            return self._serialize_result(self.db.get_item_relationships(item_id))
        
        @self.tool("get_blocking_items")
        def get_blocking_items(item_id: int) -> Dict[str, Any]:
            """Get items that block this item from being completed."""
            blockers = self.db.get_blocking_items(item_id)
            return {"success": True, "blockers": self._serialize_result(blockers), "count": len(blockers)}

        # --- Epic/Hierarchy Tools ---

        @self.tool("get_epic_progress")
        def get_epic_progress(item_id: int) -> Dict[str, Any]:
            """Get progress stats for an epic: total, completed, percent, incomplete_items."""
            progress = self.db.get_epic_progress(item_id)
            return {"success": True, "progress": self._serialize_result(progress)}

        @self.tool("set_parent")
        def set_parent(item_id: int, parent_id: int) -> Dict[str, Any]:
            """Set or remove parent relationship. Use parent_id=0 to remove parent."""
            result = self.db.set_parent(item_id, parent_id if parent_id else None)
            return self._serialize_result(result)

        @self.tool("list_children")
        def list_children(item_id: int, recursive: bool = False) -> Dict[str, Any]:
            """Get children of an item. Set recursive=True to get all descendants."""
            if recursive:
                children = self.db.get_all_descendants(item_id)
            else:
                children = self.db.get_children(item_id)
            return {"success": True, "children": self._serialize_result(children), "count": len(children)}

        # --- Tag Tools ---

        @self.tool("list_tags")
        def list_tags() -> Dict[str, Any]:
            """List all tags in current project with usage counts."""
            project_id = self._get_project_id()
            tags = self.db.get_project_tags(project_id)
            return {"success": True, "tags": self._serialize_result(tags), "count": len(tags)}

        @self.tool("add_tag")
        def add_tag(item_id: int, tag_name: str) -> Dict[str, Any]:
            """Add a tag to an item (creates tag if it doesn't exist)."""
            result = self.db.add_tag_to_item(item_id, tag_name)
            return self._serialize_result(result)

        @self.tool("remove_tag")
        def remove_tag(item_id: int, tag_id: int) -> Dict[str, Any]:
            """Remove a tag from an item."""
            result = self.db.remove_tag_from_item(item_id, tag_id)
            return self._serialize_result(result)

        @self.tool("get_item_tags")
        def get_item_tags(item_id: int) -> Dict[str, Any]:
            """Get all tags assigned to an item."""
            tags = self.db.get_item_tags(item_id)
            return {"success": True, "tags": self._serialize_result(tags), "count": len(tags)}

        @self.tool("update_tag")
        def update_tag(tag_id: int, name: str = "", color: str = "") -> Dict[str, Any]:
            """Update tag name and/or color."""
            result = self.db.update_tag(
                tag_id,
                name=name if name else None,
                color=color if color else None
            )
            return self._serialize_result(result)

        @self.tool("delete_tag")
        def delete_tag(tag_id: int) -> Dict[str, Any]:
            """Delete a tag from current project (removes from all items)."""
            result = self.db.delete_tag(tag_id)
            return self._serialize_result(result)

        # --- Status History Tools ---

        @self.tool("get_status_history")
        def get_status_history(item_id: int) -> Dict[str, Any]:
            """Get status change history for an item, ordered chronologically."""
            history = self.db.get_status_history(item_id)
            return {"success": True, "history": self._serialize_result(history), "count": len(history)}

        @self.tool("get_item_metrics")
        def get_item_metrics(item_id: int) -> Dict[str, Any]:
            """Get calculated metrics for an item: lead_time, cycle_time, time_in_each_status, revert_count, current_age (all times in hours)."""
            metrics = self.db.get_item_metrics(item_id)
            if metrics:
                return {"success": True, "metrics": self._serialize_result(metrics)}
            return {"success": False, "error": "Item not found or no history"}

        # --- Export Tool ---

        @self.tool("export_project")
        def export_project(
            format: str = "json",
            item_type: str = "",
            status: str = "",
            item_ids: str = "",
            include_tags: bool = True,
            include_relationships: bool = False,
            include_metrics: bool = False,
            include_updates: bool = False,
            include_epic_progress: bool = False,
            detailed: bool = False,
            limit: int = 500
        ) -> Dict[str, Any]:
            """Export project data in JSON, YAML, or Markdown format.

            Args:
                format: Output format - 'json', 'yaml', or 'markdown'
                item_type: Filter by type (issue, feature, epic, todo, diary, question)
                status: Filter by status (backlog, todo, in_progress, review, done, closed)
                item_ids: Comma-separated item IDs to export (overrides type/status filters)
                include_tags: Include tag data for each item (default: True)
                include_relationships: Include relationship data
                include_metrics: Include calculated metrics (lead_time, cycle_time, etc.)
                include_updates: Include project updates
                include_epic_progress: Include epic progress stats
                detailed: For markdown, show detailed item info instead of tables
                limit: Maximum items to export (default: 500)

            Returns:
                Dict with success, format, content, and item_count
            """
            from kanban_mcp.export import get_file_extension
            import tempfile

            project_id = self._get_project_id()

            # Parse item_ids if provided
            parsed_item_ids = None
            if item_ids:
                parsed_item_ids = [int(x.strip()) for x in item_ids.split(',') if x.strip()]

            try:
                # Build export data
                builder = ExportBuilder(self.db, project_id)
                data = builder.build_export_data(
                    item_ids=parsed_item_ids,
                    item_type=item_type if item_type else None,
                    status=status if status else None,
                    include_tags=include_tags,
                    include_relationships=include_relationships,
                    include_metrics=include_metrics,
                    include_updates=include_updates,
                    include_epic_progress=include_epic_progress,
                    limit=limit
                )

                # Format output
                content = export_to_format(data, format=format, detailed=detailed)

                # Write to temp file
                project = self.db.get_project_by_id(project_id)
                project_name = project['name'] if project else 'export'
                safe_name = ''.join(c for c in project_name if c.isalnum() or c in '-_')[:50]
                ext = get_file_extension(format)

                with tempfile.NamedTemporaryFile(
                    mode='w',
                    prefix=f'{safe_name}_',
                    suffix=ext,
                    delete=False,
                    encoding='utf-8'
                ) as f:
                    f.write(content)
                    file_path = f.name

                return {
                    "success": True,
                    "format": format,
                    "file_path": file_path,
                    "item_count": len(data.get("items", []))
                }
            except ImportError as e:
                return {"success": False, "error": str(e)}
            except ValueError as e:
                return {"success": False, "error": str(e)}

        # --- Search Tool ---

        @self.tool("search")
        def search(query: str, limit: int = 20) -> Dict[str, Any]:
            """Full-text search across items and updates in current project.

            Args:
                query: Search query string
                limit: Maximum results per category (default 20)

            Returns:
                Dict with items, updates, and total_count
            """
            project_id = self._get_project_id()
            results = self.db.search(project_id, query, limit)
            return {
                "success": True,
                "items": self._serialize_result(results['items']),
                "updates": self._serialize_result(results['updates']),
                "total_count": results['total_count']
            }

        # --- File Linking Tools ---

        @self.tool("link_file")
        def link_file(item_id: int, file_path: str, line_start: int = None, line_end: int = None) -> Dict[str, Any]:
            """Link a file (or file region) to an item.

            Args:
                item_id: The item to link the file to
                file_path: Relative path to the file
                line_start: Optional starting line number
                line_end: Optional ending line number

            Returns:
                Dict with success status and link_id if successful
            """
            try:
                result = self.db.link_file(item_id, file_path, line_start, line_end)
                return result
            except ValueError as e:
                return {"success": False, "error": str(e)}

        @self.tool("unlink_file")
        def unlink_file(item_id: int, file_path: str, line_start: int = None, line_end: int = None) -> Dict[str, Any]:
            """Remove a file link from an item.

            Args:
                item_id: The item to unlink the file from
                file_path: Relative path to the file
                line_start: Optional starting line number (must match to unlink)
                line_end: Optional ending line number (must match to unlink)

            Returns:
                Dict with success status
            """
            return self.db.unlink_file(item_id, file_path, line_start, line_end)

        @self.tool("get_item_files")
        def get_item_files(item_id: int) -> Dict[str, Any]:
            """Get all files linked to an item.

            Args:
                item_id: The item ID to get files for

            Returns:
                Dict with success status and list of files
            """
            files = self.db.get_item_files(item_id)
            return {
                "success": True,
                "count": len(files),
                "files": self._serialize_result(files)
            }

        # --- Decision History Tools ---

        @self.tool("add_decision")
        def add_decision(item_id: int, choice: str, rejected_alternatives: str = "",
                         rationale: str = "") -> Dict[str, Any]:
            """Add a decision record to an item.

            Args:
                item_id: The item to attach the decision to
                choice: What was decided (max 200 chars)
                rejected_alternatives: What was rejected (max 500 chars)
                rationale: Brief reason for the choice (max 200 chars)
            """
            try:
                result = self.db.add_decision(
                    item_id,
                    choice,
                    rejected_alternatives if rejected_alternatives else None,
                    rationale if rationale else None
                )
                return result
            except ValueError as e:
                return {"success": False, "error": str(e)}

        @self.tool("get_item_decisions")
        def get_item_decisions(item_id: int) -> Dict[str, Any]:
            """Get all decisions for an item."""
            decisions = self.db.get_item_decisions(item_id)
            return {
                "success": True,
                "count": len(decisions),
                "decisions": self._serialize_result(decisions)
            }

        @self.tool("delete_decision")
        def delete_decision(decision_id: int) -> Dict[str, Any]:
            """Delete a decision record."""
            return self.db.delete_decision(decision_id)

        # --- Semantic Search Tools ---

        @self.tool("semantic_search")
        def semantic_search(query: str, limit: int = 10, source_types: str = "",
                           threshold: float = 0.0) -> Dict[str, Any]:
            """Search items, decisions, and updates by semantic similarity.

            Args:
                query: Natural language search query
                limit: Maximum results to return (default: 10)
                source_types: Comma-separated types to search (item,decision,update). Empty = all
                threshold: Minimum similarity score 0.0-1.0 (default: 0.0)

            Returns:
                Dict with success, results list (each with source_type, source_id, similarity, title/snippet)
            """
            project_id = self._get_project_id()
            type_list = [t.strip() for t in source_types.split(',') if t.strip()] if source_types else None
            results = self.db.semantic_search(
                project_id=project_id,
                query=query,
                limit=limit,
                source_types=type_list,
                threshold=threshold
            )
            return {
                "success": True,
                "results": self._serialize_result(results),
                "count": len(results)
            }

        @self.tool("find_similar")
        def find_similar(source_type: str, source_id: int, limit: int = 5,
                        threshold: float = 0.0) -> Dict[str, Any]:
            """Find items similar to a given item, decision, or update.

            Args:
                source_type: Type of source ('item', 'decision', 'update')
                source_id: ID of the source to find similar to
                limit: Maximum results (default: 5)
                threshold: Minimum similarity 0.0-1.0 (default: 0.0)

            Returns:
                Dict with success, results list (excluding the source itself)
            """
            results = self.db.find_similar(
                source_type=source_type,
                source_id=source_id,
                limit=limit,
                threshold=threshold
            )
            return {
                "success": True,
                "results": self._serialize_result(results),
                "count": len(results)
            }

        @self.tool("rebuild_embeddings")
        def rebuild_embeddings(source_types: str = "") -> Dict[str, Any]:
            """Rebuild all embeddings for the current project.

            Args:
                source_types: Comma-separated types to rebuild (item,decision,update). Empty = all

            Returns:
                Dict with success, processed count, and any errors
            """
            project_id = self._get_project_id()
            type_list = [t.strip() for t in source_types.split(',') if t.strip()] if source_types else None
            result = self.db.rebuild_embeddings(project_id, type_list)
            return self._serialize_result(result)

        # --- Timeline Tools ---

        @self.tool("get_item_timeline")
        def get_item_timeline(item_id: int, limit: int = 100) -> Dict[str, Any]:
            """Get activity timeline for a specific item.

            Returns unified timeline of status changes, decisions, updates, and git commits.

            Args:
                item_id: The item to get timeline for
                limit: Maximum entries to return (default: 100)

            Returns:
                Dict with success, entries list (sorted by timestamp desc), entry_count
            """
            # Get repo path for git integration
            repo_path = self.current_project_path

            result = self.db.get_timeline_data(
                item_id=item_id,
                limit=limit,
                repo_path=repo_path
            )
            return self._serialize_result(result)

        @self.tool("get_project_timeline")
        def get_project_timeline(limit: int = 100) -> Dict[str, Any]:
            """Get activity timeline for the entire project.

            Returns unified timeline of all status changes, decisions, updates, and git commits.

            Args:
                limit: Maximum entries to return (default: 100)

            Returns:
                Dict with success, entries list (sorted by timestamp desc), entry_count
            """
            project_id = self._get_project_id()
            repo_path = self.current_project_path

            result = self.db.get_timeline_data(
                project_id=project_id,
                limit=limit,
                repo_path=repo_path
            )
            return self._serialize_result(result)

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
