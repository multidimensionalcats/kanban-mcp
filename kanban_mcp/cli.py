#!/usr/bin/env python3
"""
Kanban CLI - Command-line interface for Claude Code hooks.
Shares KanbanDB with the MCP server for consistent data access.
"""

import argparse
import json
import sys
from pathlib import Path

from kanban_mcp.core import KanbanDB
from kanban_mcp.export import ExportBuilder, export_to_format


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


def do_search(db: KanbanDB, project_path: str, query: str, limit: int = 20, format: str = "text") -> str:
    """Search items and updates."""
    project_id = db.ensure_project(project_path)
    results = db.search(project_id, query, limit)

    if format == "json":
        return json.dumps(results, indent=2, default=str)

    if results['total_count'] == 0:
        return "No results found"

    lines = [f"## Search results for: {query}"]

    if results['items']:
        lines.append(f"\n### Items ({len(results['items'])})")
        for item in results['items']:
            snippet = f" - {item['snippet'][:50]}..." if item.get('snippet') else ""
            lines.append(f"- [{item['type_name']}#{item['id']}] {item['title']} ({item['status_name']}){snippet}")

    if results['updates']:
        lines.append(f"\n### Updates ({len(results['updates'])})")
        for update in results['updates']:
            snippet = update.get('snippet', '')[:60]
            lines.append(f"- {snippet}...")

    return "\n".join(lines)


def do_semantic_search(
    db: KanbanDB,
    project_path: str,
    query: str,
    limit: int = 10,
    source_types: str = None,
    threshold: float = 0.0,
    format: str = "text"
) -> str:
    """Semantic search using vector embeddings."""
    project_id = db.ensure_project(project_path)

    type_list = None
    if source_types:
        type_list = [t.strip() for t in source_types.split(',') if t.strip()]

    results = db.semantic_search(project_id, query, limit, type_list, threshold)

    if format == "json":
        return json.dumps({"results": results, "count": len(results)}, indent=2, default=str)

    if not results:
        return "No semantic matches found"

    lines = [f"## Semantic search: {query}"]

    for r in results:
        sim = f"{r['similarity']:.0%}"
        if r['source_type'] == 'item':
            status = f" ({r.get('status_name', '')})" if r.get('status_name') else ""
            lines.append(f"- [{r.get('type_name', 'item')}#{r['source_id']}] {r.get('title', '')}{status} [{sim}]")
            if r.get('snippet'):
                lines.append(f"    {r['snippet'][:80]}...")
        elif r['source_type'] == 'decision':
            lines.append(f"- [decision#{r['source_id']}] {r.get('title', '')} [{sim}]")
        elif r['source_type'] == 'update':
            lines.append(f"- [update#{r['source_id']}] {r.get('snippet', '')[:60]}... [{sim}]")

    return "\n".join(lines)


def get_children(db: KanbanDB, project_path: str, item_id: int, recursive: bool = False, format: str = "text") -> str:
    """Get children of an item (epic)."""
    if recursive:
        children = db.get_all_descendants(item_id)
    else:
        children = db.get_children(item_id)

    if format == "json":
        return json.dumps({"children": children, "count": len(children)}, indent=2, default=str)

    if not children:
        return f"No children for item #{item_id}"

    # Get item info for header
    item = db.get_item(item_id)
    title = item['title'] if item else 'Unknown'

    lines = [f"## Children of #{item_id}: {title}"]
    for child in children:
        status = child.get('status_name', '')
        lines.append(f"- [{child['type_name']}#{child['id']}] {child['title']} ({status})")

    # Also show progress if it's an epic
    if item and item.get('type_name') == 'epic':
        progress = db.get_epic_progress(item_id)
        lines.append(f"\nProgress: {progress['completed']}/{progress['total']} ({progress['percent']}%)")

    return "\n".join(lines)


def get_files(
    db: KanbanDB,
    project_path: str,
    item_id: int,
    format: str = "text"
) -> str:
    """Get files linked to an item."""
    files = db.get_item_files(item_id)

    if format == "json":
        return json.dumps({"files": files, "count": len(files)}, indent=2, default=str)

    if not files:
        return f"No files linked to item #{item_id}"

    # Get item info for header
    item = db.get_item(item_id)
    title = item['title'] if item else 'Unknown'

    lines = [f"## Files linked to #{item_id}: {title}"]
    for f in files:
        line_info = ""
        if f.get('line_start') is not None:
            if f.get('line_end') is not None:
                line_info = f":{f['line_start']}-{f['line_end']}"
            else:
                line_info = f":{f['line_start']}"
        lines.append(f"- {f['file_path']}{line_info}")

    return "\n".join(lines)


def link_file_cmd(
    db: KanbanDB,
    project_path: str,
    item_id: int,
    file_path: str,
    line_start: int = None,
    line_end: int = None,
    format: str = "text"
) -> str:
    """Link a file to an item."""
    try:
        result = db.link_file(item_id, file_path, line_start, line_end)
        if format == "json":
            return json.dumps(result, indent=2, default=str)
        if result.get('success'):
            return f"Linked {file_path} to item #{item_id}"
        return f"Error: {result.get('error')}"
    except ValueError as e:
        if format == "json":
            return json.dumps({"success": False, "error": str(e)}, indent=2)
        return f"Error: {e}"


def unlink_file_cmd(
    db: KanbanDB,
    project_path: str,
    item_id: int,
    file_path: str,
    line_start: int = None,
    line_end: int = None,
    format: str = "text"
) -> str:
    """Unlink a file from an item."""
    result = db.unlink_file(item_id, file_path, line_start, line_end)
    if format == "json":
        return json.dumps(result, indent=2, default=str)
    if result.get('success'):
        return f"Unlinked {file_path} from item #{item_id}"
    return f"Error: {result.get('error')}"


def rebuild_embeddings(
    db: KanbanDB,
    project_path: str = None,
    source_types: str = None,
    all_projects: bool = False,
    format: str = "text"
) -> str:
    """Rebuild embeddings for a project or all projects."""
    type_list = None
    if source_types:
        type_list = [t.strip() for t in source_types.split(',') if t.strip()]

    if all_projects:
        result = db.rebuild_all_embeddings(type_list)
    else:
        if not project_path:
            return "Error: --project required (or use --all)"
        project_id = db.ensure_project(project_path)
        result = db.rebuild_embeddings(project_id, type_list)

    if format == "json":
        return json.dumps(result, indent=2, default=str)

    if result.get('success'):
        msg = f"Rebuilt {result['processed']} embeddings"
        if result.get('errors'):
            msg += f" ({len(result['errors'])} errors)"
        return msg
    return f"Error: {result.get('error')}"


def export_data(
    db: KanbanDB,
    project_path: str,
    format: str = "json",
    item_type: str = None,
    status: str = None,
    item_ids: str = None,
    include_tags: bool = True,
    include_relationships: bool = False,
    include_metrics: bool = False,
    include_updates: bool = False,
    include_epic_progress: bool = False,
    detailed: bool = False,
    limit: int = 500,
    output: str = None
) -> str:
    """Export project data in various formats."""
    project_id = db.ensure_project(project_path)

    # Parse item IDs if provided
    parsed_item_ids = None
    if item_ids:
        try:
            parsed_item_ids = [int(x.strip()) for x in item_ids.split(',') if x.strip()]
        except ValueError:
            return "Error: Invalid item IDs — must be comma-separated integers (e.g. '1,2,3')"

    # Build export data
    builder = ExportBuilder(db, project_id)
    data = builder.build_export_data(
        item_ids=parsed_item_ids,
        item_type=item_type,
        status=status,
        include_tags=include_tags,
        include_relationships=include_relationships,
        include_metrics=include_metrics,
        include_updates=include_updates,
        include_epic_progress=include_epic_progress,
        limit=limit
    )

    # Format output
    content = export_to_format(data, format=format, detailed=detailed)

    # Write to file if output specified
    if output:
        with open(output, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Exported {len(data.get('items', []))} items to {output}"

    return content


def main():
    parser = argparse.ArgumentParser(
        description="Kanban CLI for Claude Code hooks",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--project", "-p",
        required=False,
        help="Project directory path (usually $PWD). Required for most commands."
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

    # Children command
    children_parser = subparsers.add_parser("children", help="Get children of an item (epic)")
    children_parser.add_argument("item_id", type=int, help="Item ID to get children for")
    children_parser.add_argument("--recursive", "-r", action="store_true", help="Include all descendants")

    # Search command (keyword)
    search_parser = subparsers.add_parser("search", help="Search items and updates (keyword)")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--limit", "-l", type=int, default=20, help="Max results (default: 20)")

    # Semantic search command
    sem_parser = subparsers.add_parser("semantic-search", help="Semantic search using AI embeddings")
    sem_parser.add_argument("query", help="Natural language search query")
    sem_parser.add_argument("--limit", "-l", type=int, default=10, help="Max results (default: 10)")
    sem_parser.add_argument("--types", "-t", help="Source types: item,decision,update (default: all)")
    sem_parser.add_argument("--threshold", type=float, default=0.0, help="Min similarity 0.0-1.0 (default: 0.0)")

    # Rebuild embeddings command
    embed_parser = subparsers.add_parser("rebuild-embeddings", help="Rebuild vector embeddings for semantic search")
    embed_parser.add_argument("--types", "-t", help="Comma-separated types to rebuild (item,decision,update). Default: all")
    embed_parser.add_argument("--all", "-a", action="store_true", dest="all_projects", help="Rebuild for ALL projects (ignores -p)")

    # Files command with subcommands
    files_parser = subparsers.add_parser("files", help="Manage file links for an item")
    files_parser.add_argument("item_id", type=int, help="Item ID to manage files for")
    files_subparsers = files_parser.add_subparsers(dest="files_action", help="Action to perform")

    # List files (default if no action)
    files_subparsers.add_parser("list", help="List files linked to item (default)")

    # Link file
    link_parser = files_subparsers.add_parser("link", help="Link a file to the item")
    link_parser.add_argument("file_path", help="Relative path to the file")
    link_parser.add_argument("--start", type=int, help="Starting line number")
    link_parser.add_argument("--end", type=int, help="Ending line number")

    # Unlink file
    unlink_parser = files_subparsers.add_parser("unlink", help="Unlink a file from the item")
    unlink_parser.add_argument("file_path", help="Relative path to the file")
    unlink_parser.add_argument("--start", type=int, help="Starting line number (must match)")
    unlink_parser.add_argument("--end", type=int, help="Ending line number (must match)")

    # Export command with additional options
    export_parser = subparsers.add_parser("export", help="Export project data")
    export_parser.add_argument(
        "--format", "-F",
        choices=["json", "yaml", "markdown"],
        default="json",
        help="Output format (default: json)"
    )
    export_parser.add_argument(
        "--type", "-t",
        dest="item_type",
        help="Filter by item type (issue, feature, epic, todo, diary, question)"
    )
    export_parser.add_argument(
        "--status", "-s",
        help="Filter by status (backlog, todo, in_progress, review, done, closed)"
    )
    export_parser.add_argument(
        "--ids",
        dest="item_ids",
        help="Comma-separated item IDs to export"
    )
    export_parser.add_argument(
        "--no-tags",
        action="store_true",
        help="Exclude tags from export"
    )
    export_parser.add_argument(
        "--relationships",
        action="store_true",
        help="Include relationship data"
    )
    export_parser.add_argument(
        "--metrics",
        action="store_true",
        help="Include metrics data"
    )
    export_parser.add_argument(
        "--updates",
        action="store_true",
        help="Include project updates"
    )
    export_parser.add_argument(
        "--epic-progress",
        action="store_true",
        help="Include epic progress stats"
    )
    export_parser.add_argument(
        "--detailed", "-d",
        action="store_true",
        help="For markdown, show detailed item info instead of tables"
    )
    export_parser.add_argument(
        "--limit", "-l",
        type=int,
        default=500,
        help="Maximum items to export (default: 500)"
    )
    export_parser.add_argument(
        "--output", "-o",
        help="Output file path (prints to stdout if not specified)"
    )
    
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Check if --project is required for this command
    all_projects = getattr(args, 'all_projects', False)
    if args.command == "rebuild-embeddings" and all_projects:
        pass  # --project not required when using --all
    elif not args.project:
        print("Error: --project/-p is required for this command", file=sys.stderr)
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
        if args.command == "export":
            # Export command has special arguments
            result = export_data(
                db,
                args.project,
                format=args.format,
                item_type=getattr(args, 'item_type', None),
                status=getattr(args, 'status', None),
                item_ids=getattr(args, 'item_ids', None),
                include_tags=not getattr(args, 'no_tags', False),
                include_relationships=getattr(args, 'relationships', False),
                include_metrics=getattr(args, 'metrics', False),
                include_updates=getattr(args, 'updates', False),
                include_epic_progress=getattr(args, 'epic_progress', False),
                detailed=getattr(args, 'detailed', False),
                limit=getattr(args, 'limit', 500),
                output=getattr(args, 'output', None)
            )
        elif args.command == "children":
            result = get_children(
                db,
                args.project,
                args.item_id,
                recursive=getattr(args, 'recursive', False),
                format=args.format
            )
        elif args.command == "search":
            result = do_search(
                db,
                args.project,
                args.query,
                limit=getattr(args, 'limit', 20),
                format=args.format
            )
        elif args.command == "semantic-search":
            result = do_semantic_search(
                db,
                args.project,
                args.query,
                limit=getattr(args, 'limit', 10),
                source_types=getattr(args, 'types', None),
                threshold=getattr(args, 'threshold', 0.0),
                format=args.format
            )
        elif args.command == "rebuild-embeddings":
            result = rebuild_embeddings(
                db,
                project_path=args.project if not getattr(args, 'all_projects', False) else None,
                source_types=getattr(args, 'types', None),
                all_projects=getattr(args, 'all_projects', False),
                format=args.format
            )
        elif args.command == "files":
            # Files command with subcommands
            action = getattr(args, 'files_action', None) or 'list'
            if action == 'link':
                result = link_file_cmd(
                    db,
                    args.project,
                    args.item_id,
                    args.file_path,
                    line_start=getattr(args, 'start', None),
                    line_end=getattr(args, 'end', None),
                    format=args.format
                )
            elif action == 'unlink':
                result = unlink_file_cmd(
                    db,
                    args.project,
                    args.item_id,
                    args.file_path,
                    line_start=getattr(args, 'start', None),
                    line_end=getattr(args, 'end', None),
                    format=args.format
                )
            else:  # list or default
                result = get_files(
                    db,
                    args.project,
                    args.item_id,
                    format=args.format
                )
        else:
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
