#!/usr/bin/env python3
"""
Kanban Stop hook for Claude Code.
Reminds to create a diary entry when session ends.
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
        sys.exit(0)
    
    try:
        db = KanbanDB()
        project_id = db.hash_project_path(project_dir)
        
        # Check if project exists
        project = db.get_project_by_id(project_id)
        if not project:
            sys.exit(0)
        
        # Get session summary
        active_items = db.list_items(project_id=project_id, status_name="in_progress", limit=10)
        summary = db.project_summary(project_id)
        
        # Output reminder
        print(f"\n[Kanban: {project['name']} - Session End]")
        
        if active_items:
            print("Items still in progress:")
            for item in active_items:
                print(f"  • #{item['id']} {item['title']}")
        
        print("\nConsider:")
        print("  • Creating a diary entry to summarize this session")
        print("  • Updating item statuses if work was completed")
        print("  • Adding progress updates to tracked items")
        print()
        
    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()
