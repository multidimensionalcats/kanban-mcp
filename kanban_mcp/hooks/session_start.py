#!/usr/bin/env python3
"""
Kanban SessionStart hook for Claude Code.
Injects active items context at the start of a session.
"""

import json
import os
import sys

from kanban_mcp.core import KanbanDB


def main():
    # Read hook input from stdin
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        hook_input = {}
    
    # Get project directory from environment or hook input
    project_dir = os.environ.get('CLAUDE_PROJECT_DIR') or hook_input.get('cwd')
    
    if not project_dir:
        sys.exit(0)  # No project context, exit silently
    
    try:
        db = KanbanDB()
        project_id = db.hash_project_path(project_dir)
        
        # Check if project exists
        project = db.get_project_by_id(project_id)
        if not project:
            sys.exit(0)  # Project not tracked, exit silently
        
        # Get active items
        active_items = db.list_items(project_id=project_id, status_name="in_progress", limit=10)
        
        if not active_items:
            sys.exit(0)  # No active items, exit silently
        
        # Output context to inject into conversation
        print(f"\n[Kanban: {project['name']}]")
        print("Currently in progress:")
        for item in active_items:
            desc = f" - {item['description'][:80]}..." if item.get('description') else ""
            print(f"  • #{item['id']} [{item['type_name']}] {item['title']}{desc}")
        print()
        
    except Exception as e:
        # Don't block session start on errors
        sys.exit(0)


if __name__ == "__main__":
    main()
