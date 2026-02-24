#!/usr/bin/env python3
"""
Kanban CLI - Command-line interface for Claude Code hooks.
Shares KanbanDB with the MCP server for consistent data access.
"""

import argparse
import json
import sys
from pathlib import Path

# Import shared database class
from kanban_mcp import KanbanDB


def get_active_items(db: KanbanDB, project_path: str, format: str = "text") -> str:
    """Get items currently in progress."""
    project_id = db.ensure_project(project_path)
    items = db.list_items(project_id=project_id, status_name="in_progress", limit=20)
    
    if format == "json":
        return json.dumps({"items": items, "count": len(items)}, indent=2, default=str)
    
    if not items:
        return ""
    
    lines = ["## Active Items (in_progress)"]
    for item in items:
        lines.append(f"- [{item['type_name']}#{item['id']}] {item['title']} (priority {item['priority']})")
    return "\n".join(lines)


def get_todos(db: KanbanDB, project_path: str, format: str = "text") -> str:
    """Get items in backlog."""
    project_id = db.ensure_project(project_path)
    items = db.list_items(project_id=project_id, status_name="backlog", limit=20)
    
    if format == "json":
        return json.dumps({"items": items, "count": len(items)}, indent=2, default=str)
    
    if not items:
        return ""
    
    lines = ["## Backlog"]
    for item in items:
        lines.append(f"- [{item['type_name']}#{item['id']}] {item['title']} (priority {item['priority']})")
    return "\n".join(lines)


def get_summary(db: KanbanDB, project_path: str, format: str = "text") -> str:
    """Get project summary."""
    project_id = db.ensure_project(project_path)
    summary = db.project_summary(project_id)
    project = db.get_project_by_id(project_id)
    
    if format == "json":
        return json.dumps({"project": project, "summary": summary}, indent=2, default=str)
    
    if not summary:
        return ""
    
    lines = [f"## Project: {project['name'] if project else 'Unknown'}"]
    for type_name, statuses in summary.items():
        status_parts = [f"{status}: {count}" for status, count in statuses.items()]
        lines.append(f"- {type_name}: {', '.join(status_parts)}")
    return "\n".join(lines)


def get_context(db: KanbanDB, project_path: str, format: str = "text") -> str:
    """Get full context for hook injection (active items + summary)."""
    project_id = db.ensure_project(project_path)
    project = db.get_project_by_id(project_id)
    active = db.list_items(project_id=project_id, status_name="in_progress", limit=10)
    summary = db.project_summary(project_id)
    
    if format == "json":
        return json.dumps({
            "project": project,
            "active_items": active,
            "summary": summary
        }, indent=2, default=str)
    
    # Text format for hook injection
    lines = []
    
    if active:
        lines.append(f"[Kanban: {project['name'] if project else 'project'}]")
        lines.append("Active items:")
        for item in active:
            desc = f" - {item['description'][:60]}..." if item.get('description') else ""
            lines.append(f"  • #{item['id']} {item['title']}{desc}")
    
    return "\n".join(lines)


def get_latest_update(db: KanbanDB, project_path: str, format: str = "text") -> str:
    """Get most recent update."""
    project_id = db.ensure_project(project_path)
    update = db.get_latest_update(project_id)
    
    if format == "json":
        return json.dumps({"update": update}, indent=2, default=str)
    
    if not update:
        return ""
    
    return f"Last update: {update['content']}"


def main():
    parser = argparse.ArgumentParser(
        description="Kanban CLI for Claude Code hooks",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--project", "-p",
        required=True,
        help="Project directory path (usually $PWD)"
    )
    parser.add_argument(
        "--format", "-f",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Commands
    subparsers.add_parser("active", help="Get active (in_progress) items")
    subparsers.add_parser("todos", help="Get backlog items")
    subparsers.add_parser("summary", help="Get project summary")
    subparsers.add_parser("context", help="Get full context for hooks")
    subparsers.add_parser("latest-update", help="Get most recent update")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    db = KanbanDB()
    
    commands = {
        "active": get_active_items,
        "todos": get_todos,
        "summary": get_summary,
        "context": get_context,
        "latest-update": get_latest_update,
    }
    
    try:
        result = commands[args.command](db, args.project, args.format)
        if result:
            print(result)
    except Exception as e:
        if args.format == "json":
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
