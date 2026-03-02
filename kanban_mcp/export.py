#!/usr/bin/env python3
"""
Kanban Export Module
Provides multi-format export functionality
(JSON, YAML, Markdown) for kanban data.
"""

import json
from datetime import datetime
from typing import Dict, List, Any, Optional

# YAML is optional - gracefully handle missing import
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


class ExportBuilder:
    """Gathers kanban data with filtering options for export."""

    def __init__(self, db, project_id: str):
        """Initialize exporter with database connection and project.

        Args:
            db: KanbanDB instance
            project_id: Project ID to export
        """
        self.db = db
        self.project_id = project_id
        self.project = db.get_project_by_id(project_id)

    def build_export_data(
        self,
        item_ids: List[int] = None,
        item_type: str = None,
        status: str = None,
        include_tags: bool = True,
        include_relationships: bool = False,
        include_metrics: bool = False,
        include_updates: bool = False,
        include_epic_progress: bool = False,
        include_decisions: bool = False,
        limit: int = 500
    ) -> Dict[str, Any]:
        """Build complete export data structure.

        Args:
            item_ids: Optional list of specific item IDs to include
            item_type: Filter by item type
                (issue, feature, epic, todo, diary, question)
            status: Filter by status
                (backlog, todo, in_progress, review, done, closed)
            include_tags: Include tag data for each item
            include_relationships: Include relationship data
            include_metrics: Include calculated metrics
                (lead_time, cycle_time, etc.)
            include_updates: Include project updates
            include_epic_progress: Include epic progress stats
            include_decisions: Include decision history for items
            limit: Maximum items to export

        Returns:
            Complete export data dictionary
        """
        # Build metadata
        metadata = {
            "project_name": (
                self.project['name'] if self.project
                else "Unknown"
            ),
            "project_path": (
                self.project['directory_path']
                if self.project else None
            ),
            "exported_at": datetime.now().isoformat(),
            "filters": {
                "item_ids": item_ids,
                "item_type": item_type,
                "status": status,
                "limit": limit
            },
            "include_options": {
                "tags": include_tags,
                "relationships": include_relationships,
                "metrics": include_metrics,
                "updates": include_updates,
                "epic_progress": include_epic_progress,
                "decisions": include_decisions
            }
        }

        # Get items based on filters
        if item_ids:
            items = [self.db.get_item(item_id) for item_id in item_ids]
            items = [i for i in items if i is not None]
        else:
            items = self.db.list_items(
                project_id=self.project_id,
                type_name=item_type if item_type else None,
                status_name=status if status else None,
                limit=limit
            )

        # Process items and add optional data
        processed_items = []
        for item in items:
            processed = self._process_item(
                item,
                include_tags=include_tags,
                include_relationships=include_relationships,
                include_metrics=include_metrics,
                include_epic_progress=include_epic_progress,
                include_decisions=include_decisions
            )
            processed_items.append(processed)

        # Build export data
        export_data = {
            "metadata": metadata,
            "items": processed_items,
            "summary": self._build_summary(processed_items)
        }

        # Include updates if requested
        if include_updates:
            updates = self.db.get_updates(self.project_id, limit=100)
            export_data["updates"] = self._serialize_updates(updates)

        return export_data

    def _process_item(
        self,
        item: Dict,
        include_tags: bool,
        include_relationships: bool,
        include_metrics: bool,
        include_epic_progress: bool,
        include_decisions: bool = False
    ) -> Dict[str, Any]:
        """Process a single item for export."""
        processed = {
            "id": item['id'],
            "title": item['title'],
            "description": item.get('description'),
            "type_name": item['type_name'],
            "status_name": item['status_name'],
            "priority": item['priority'],
            "complexity": item.get('complexity'),
            "parent_id": item.get('parent_id'),
            "created_at": self._serialize_datetime(item.get('created_at')),
            "closed_at": self._serialize_datetime(item.get('closed_at'))
        }

        if include_tags:
            tags = self.db.get_item_tags(item['id'])
            processed["tags"] = [
                {"id": t['id'], "name": t['name'], "color": t['color']}
                for t in tags
            ]

        if include_relationships:
            rels = self.db.get_item_relationships(item['id'])
            processed["relationships"] = {
                "outgoing": [
                    {
                        "type": r['relationship_type'],
                        "target_id": r['related_item_id'],
                        "target_title": r['related_item_title']
                    }
                    for r in rels.get('outgoing', [])
                ],
                "incoming": [
                    {
                        "type": r['relationship_type'],
                        "source_id": r['related_item_id'],
                        "source_title": r['related_item_title']
                    }
                    for r in rels.get('incoming', [])
                ]
            }

        if include_metrics:
            metrics = self.db.get_item_metrics(item['id'])
            if metrics:
                processed["metrics"] = {
                    "lead_time": metrics.get('lead_time'),
                    "cycle_time": metrics.get('cycle_time'),
                    "time_in_each_status": metrics.get(
                        'time_in_each_status', {}
                    ),
                    "revert_count": metrics.get('revert_count', 0),
                    "current_age": metrics.get('current_age')
                }

        if include_epic_progress and item['type_name'] == 'epic':
            progress = self.db.get_epic_progress(item['id'])
            processed["epic_progress"] = {
                "total": progress['total'],
                "completed": progress['completed'],
                "percent": progress['percent'],
                "incomplete_items": progress['incomplete_items']
            }

        if include_decisions:
            decisions = self.db.get_item_decisions(item['id'])
            processed["decisions"] = [
                {
                    "id": d['id'],
                    "choice": d['choice'],
                    "rejected_alternatives": d.get('rejected_alternatives'),
                    "rationale": d.get('rationale'),
                    "created_at": self._serialize_datetime(d.get('created_at'))
                }
                for d in decisions
            ]

        return processed

    def _build_summary(self, items: List[Dict]) -> Dict[str, Any]:
        """Build summary statistics from items."""
        by_type = {}
        by_status = {}

        for item in items:
            type_name = item['type_name']
            status_name = item['status_name']

            by_type[type_name] = by_type.get(type_name, 0) + 1
            by_status[status_name] = by_status.get(status_name, 0) + 1

        return {
            "total_items": len(items),
            "by_type": by_type,
            "by_status": by_status
        }

    def _serialize_updates(self, updates: List[Dict]) -> List[Dict]:
        """Serialize updates for export."""
        return [
            {
                "id": u['id'],
                "content": u['content'],
                "created_at": self._serialize_datetime(u.get('created_at')),
                "item_ids": u.get('item_ids', [])
            }
            for u in updates
        ]

    @staticmethod
    def _serialize_datetime(dt) -> Optional[str]:
        """Convert datetime to ISO string."""
        if dt is None:
            return None
        if isinstance(dt, datetime):
            return dt.isoformat()
        return str(dt)


def format_json(data: Dict[str, Any], indent: int = 2) -> str:
    """Format export data as JSON.

    Args:
        data: Export data dictionary
        indent: Indentation level (default 2)

    Returns:
        JSON string
    """
    return json.dumps(data, indent=indent, default=str)


def format_yaml(data: Dict[str, Any]) -> str:
    """Format export data as YAML.

    Args:
        data: Export data dictionary

    Returns:
        YAML string

    Raises:
        ImportError: If pyyaml is not installed
    """
    if not YAML_AVAILABLE:
        raise ImportError(
            "YAML export requires pyyaml. Install with: pip install pyyaml"
        )
    return yaml.dump(
        data, default_flow_style=False,
        allow_unicode=True, sort_keys=False
    )


def format_markdown(data: Dict[str, Any], detailed: bool = False) -> str:
    """Format export data as Markdown.

    Args:
        data: Export data dictionary
        detailed: If True, include full item details; if False, summary tables

    Returns:
        Markdown string
    """
    lines = []
    metadata = data.get("metadata", {})
    items = data.get("items", [])
    summary = data.get("summary", {})
    updates = data.get("updates", [])

    # Header
    project_name = metadata.get("project_name", "Kanban Export")
    lines.append(f"# Kanban Export: {project_name}")
    lines.append("")

    # Metadata
    exported_at = metadata.get("exported_at", "")
    if exported_at:
        # Format date nicely
        try:
            dt = datetime.fromisoformat(exported_at)
            exported_at = dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            pass
    lines.append(f"**Exported:** {exported_at}")
    lines.append(f"**Total Items:** {summary.get('total_items', 0)}")
    lines.append("")

    # Filters applied
    filters = metadata.get("filters", {})
    active_filters = []
    if filters.get("item_type"):
        active_filters.append(f"type={filters['item_type']}")
    if filters.get("status"):
        active_filters.append(f"status={filters['status']}")
    if filters.get("item_ids"):
        active_filters.append(f"ids={','.join(map(str, filters['item_ids']))}")
    if active_filters:
        lines.append(f"**Filters:** {', '.join(active_filters)}")
        lines.append("")

    # Summary section
    lines.append("## Summary")
    lines.append("")

    # By type
    by_type = summary.get("by_type", {})
    if by_type:
        lines.append("### By Type")
        for type_name, count in sorted(by_type.items()):
            lines.append(f"- **{type_name}:** {count}")
        lines.append("")

    # By status
    by_status = summary.get("by_status", {})
    if by_status:
        lines.append("### By Status")
        status_order = [
            'backlog', 'todo', 'in_progress',
            'review', 'done', 'closed'
        ]
        for status in status_order:
            if status in by_status:
                lines.append(f"- **{status}:** {by_status[status]}")
        lines.append("")

    # Items section
    if detailed:
        lines.append("## Items (Detailed)")
        lines.append("")
        for item in items:
            lines.extend(_format_item_detailed(item))
            lines.append("")
    else:
        # Group items by type
        items_by_type = {}
        for item in items:
            type_name = item['type_name']
            if type_name not in items_by_type:
                items_by_type[type_name] = []
            items_by_type[type_name].append(item)

        lines.append("## Items by Type")
        lines.append("")

        type_order = ['epic', 'feature', 'issue', 'todo', 'diary']
        for type_name in type_order:
            if type_name in items_by_type:
                lines.extend(_format_items_table(
                    type_name, items_by_type[type_name]
                ))
                lines.append("")

        # Any types not in the standard order
        for type_name in sorted(items_by_type.keys()):
            if type_name not in type_order:
                lines.extend(_format_items_table(
                    type_name, items_by_type[type_name]
                ))
                lines.append("")

    # Updates section
    if updates:
        lines.append("## Recent Updates")
        lines.append("")
        for update in updates[:20]:  # Limit to 20 updates
            created = update.get('created_at', '')
            if created:
                try:
                    dt = datetime.fromisoformat(created)
                    created = dt.strftime("%Y-%m-%d %H:%M")
                except (ValueError, TypeError):
                    pass
            content = update.get('content', '')
            item_ids = update.get('item_ids', [])
            if item_ids:
                items_str = ', '.join(f"#{i}" for i in item_ids)
                lines.append(f"- **{created}** [{items_str}]: {content}")
            else:
                lines.append(f"- **{created}**: {content}")
        lines.append("")

    return "\n".join(lines)


def _format_items_table(type_name: str, items: List[Dict]) -> List[str]:
    """Format items of a single type as a markdown table."""
    lines = []
    lines.append(f"### {type_name.title()}s")
    lines.append("")

    # Determine columns based on data
    has_tags = any(item.get('tags') for item in items)
    has_complexity = any(item.get('complexity') for item in items)

    # Header
    header = "| ID | Title | Status | Priority |"
    separator = "|---|---|---|---|"
    if has_complexity:
        header += " Complexity |"
        separator += "---|"
    if has_tags:
        header += " Tags |"
        separator += "---|"

    lines.append(header)
    lines.append(separator)

    # Rows
    for item in items:
        title = (
            item['title'][:50] + "..."
            if len(item['title']) > 50
            else item['title']
        )
        # Escape pipe characters in title
        title = title.replace("|", "\\|")
        row = (
            f"| #{item['id']} | {title} "
            f"| {item['status_name']} "
            f"| P{item['priority']} |"
        )

        if has_complexity:
            complexity = (
                f"C{item['complexity']}"
                if item.get('complexity') else "-"
            )
            row += f" {complexity} |"

        if has_tags:
            tags = item.get('tags', [])
            tag_str = ', '.join(t['name'] for t in tags) if tags else "-"
            row += f" {tag_str} |"

        lines.append(row)

    return lines


def _format_item_detailed(item: Dict) -> List[str]:
    """Format a single item with full details."""
    lines = []

    lines.append(f"### #{item['id']} - {item['title']}")
    lines.append("")
    lines.append(f"- **Type:** {item['type_name']}")
    lines.append(f"- **Status:** {item['status_name']}")
    lines.append(f"- **Priority:** P{item['priority']}")

    if item.get('complexity'):
        lines.append(f"- **Complexity:** C{item['complexity']}")

    if item.get('parent_id'):
        lines.append(f"- **Parent:** #{item['parent_id']}")

    if item.get('created_at'):
        created = item['created_at']
        if isinstance(created, str):
            try:
                dt = datetime.fromisoformat(created)
                created = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                pass
        lines.append(f"- **Created:** {created}")

    if item.get('closed_at'):
        closed = item['closed_at']
        if isinstance(closed, str):
            try:
                dt = datetime.fromisoformat(closed)
                closed = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                pass
        lines.append(f"- **Closed:** {closed}")

    # Tags
    if item.get('tags'):
        tag_names = ', '.join(t['name'] for t in item['tags'])
        lines.append(f"- **Tags:** {tag_names}")

    # Description
    if item.get('description'):
        lines.append("")
        lines.append("**Description:**")
        lines.append("")
        lines.append(item['description'])

    # Relationships
    if item.get('relationships'):
        rels = item['relationships']
        if rels.get('outgoing') or rels.get('incoming'):
            lines.append("")
            lines.append("**Relationships:**")
            for rel in rels.get('outgoing', []):
                lines.append(
                    f"  - {rel['type']} "
                    f"→ #{rel['target_id']} "
                    f"({rel['target_title']})"
                )
            for rel in rels.get('incoming', []):
                lines.append(
                    f"  - #{rel['source_id']} "
                    f"({rel['source_title']}) "
                    f"→ {rel['type']}"
                )

    # Metrics
    if item.get('metrics'):
        metrics = item['metrics']
        lines.append("")
        lines.append("**Metrics:**")
        if metrics.get('lead_time') is not None:
            lines.append(f"  - Lead Time: {metrics['lead_time']} hours")
        if metrics.get('cycle_time') is not None:
            lines.append(f"  - Cycle Time: {metrics['cycle_time']} hours")
        if metrics.get('current_age') is not None:
            lines.append(f"  - Age: {metrics['current_age']} hours")
        if metrics.get('revert_count'):
            lines.append(f"  - Reverts: {metrics['revert_count']}")

    # Epic progress
    if item.get('epic_progress'):
        prog = item['epic_progress']
        lines.append("")
        lines.append(
            f"**Epic Progress:** "
            f"{prog['completed']}/{prog['total']} "
            f"({prog['percent']}%)"
        )
        if prog.get('incomplete_items'):
            incomplete = ', '.join(
                f"#{i}"
                for i in prog['incomplete_items'][:10]
            )
            if len(prog['incomplete_items']) > 10:
                incomplete += (
                    f" ... ({len(prog['incomplete_items']) - 10}"
                    " more)"
                )
            lines.append(f"  - Incomplete: {incomplete}")

    # Decision history
    if item.get('decisions'):
        lines.append("")
        lines.append("**Decisions:**")
        for d in item['decisions']:
            lines.append(f"  - **Chose:** {d['choice']}")
            if d.get('rejected_alternatives'):
                lines.append(f"    - Rejected: {d['rejected_alternatives']}")
            if d.get('rationale'):
                lines.append(f"    - Why: {d['rationale']}")

    return lines


def export_to_format(
    data: Dict[str, Any],
    format: str = "json",
    detailed: bool = False
) -> str:
    """Export data to specified format.

    Args:
        data: Export data dictionary from ExportBuilder
        format: Output format ('json', 'yaml', 'markdown')
        detailed: For markdown, include detailed item info

    Returns:
        Formatted string

    Raises:
        ValueError: If format is not supported
        ImportError: If yaml is requested but pyyaml not installed
    """
    format = format.lower()

    if format == "json":
        return format_json(data)
    elif format == "yaml":
        return format_yaml(data)
    elif format in ("markdown", "md"):
        return format_markdown(data, detailed=detailed)
    else:
        raise ValueError(
            f"Unsupported format: {format}. "
            "Use 'json', 'yaml', or 'markdown'"
        )


def get_mime_type(format: str) -> str:
    """Get MIME type for export format.

    Args:
        format: Export format

    Returns:
        MIME type string
    """
    format = format.lower()
    mime_types = {
        "json": "application/json",
        "yaml": "text/yaml",
        "markdown": "text/markdown",
        "md": "text/markdown"
    }
    return mime_types.get(format, "text/plain")


def get_file_extension(format: str) -> str:
    """Get file extension for export format.

    Args:
        format: Export format

    Returns:
        File extension (including dot)
    """
    format = format.lower()
    extensions = {
        "json": ".json",
        "yaml": ".yaml",
        "markdown": ".md",
        "md": ".md"
    }
    return extensions.get(format, ".txt")
