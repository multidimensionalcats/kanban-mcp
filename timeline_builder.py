#!/usr/bin/env python3
"""Timeline builder for kanban-mcp.

Aggregates activity from multiple sources into a unified timeline.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from kanban_mcp import KanbanDB
    from git_timeline import GitTimelineProvider

logger = logging.getLogger(__name__)


# Activity type icons (Material Icons names)
ACTIVITY_ICONS = {
    'status_change': 'swap_horiz',
    'decision': 'gavel',
    'update': 'comment',
    'commit': 'commit',
    'create': 'add_circle'
}

# Activity type colors (CSS class suffixes)
ACTIVITY_COLORS = {
    'status_change': 'green',
    'decision': 'purple',
    'update': 'blue',
    'commit': 'orange',
    'create': 'teal'
}


class TimelineBuilder:
    """Builds unified activity timelines from multiple data sources.

    Sources:
    - Status changes (from status_history table)
    - Decisions (from item_decisions table)
    - Updates (from updates + update_items tables)
    - Git commits (via GitTimelineProvider)
    """

    def __init__(self, db: 'KanbanDB', git_provider: Optional['GitTimelineProvider'] = None):
        """Initialize the timeline builder.

        Args:
            db: KanbanDB instance for database queries
            git_provider: Optional GitTimelineProvider for git integration
        """
        self.db = db
        self.git_provider = git_provider

    def _get_status_activities(self, item_id: int) -> List[Dict[str, Any]]:
        """Get status change activities for an item.

        Args:
            item_id: The item ID to get status changes for

        Returns:
            List of timeline entries for status changes
        """
        history = self.db.get_status_history(item_id)
        entries = []

        for entry in history:
            # Determine title based on change type
            if entry['change_type'] == 'create':
                title = f"Created in {entry['new_status']}"
            elif entry['change_type'] == 'revert':
                title = f"Reverted from {entry['old_status']} to {entry['new_status']}"
            elif entry['change_type'] == 'set':
                title = f"Status set to {entry['new_status']}"
            else:  # advance
                title = f"Moved from {entry['old_status']} to {entry['new_status']}"

            entries.append({
                'timestamp': entry['changed_at'],
                'activity_type': 'status_change',
                'item_id': item_id,
                'title': title,
                'details': {
                    'old_status': entry['old_status'],
                    'new_status': entry['new_status'],
                    'change_type': entry['change_type']
                },
                'actor': None,
                'icon': ACTIVITY_ICONS['status_change'],
                'color': ACTIVITY_COLORS['status_change']
            })

        return entries

    def _get_decision_activities(self, item_id: int) -> List[Dict[str, Any]]:
        """Get decision activities for an item.

        Args:
            item_id: The item ID to get decisions for

        Returns:
            List of timeline entries for decisions
        """
        decisions = self.db.get_item_decisions(item_id)
        entries = []

        for decision in decisions:
            entries.append({
                'timestamp': decision['created_at'],
                'activity_type': 'decision',
                'item_id': item_id,
                'title': f"Decision: {decision['choice'][:50]}{'...' if len(decision['choice']) > 50 else ''}",
                'details': {
                    'decision_id': decision['id'],
                    'choice': decision['choice'],
                    'rejected': decision.get('rejected_alternatives'),
                    'rationale': decision.get('rationale')
                },
                'actor': None,
                'icon': ACTIVITY_ICONS['decision'],
                'color': ACTIVITY_COLORS['decision']
            })

        return entries

    def _get_update_activities(self, item_id: int = None, project_id: str = None,
                               limit: int = 100) -> List[Dict[str, Any]]:
        """Get update activities for an item or project.

        Args:
            item_id: Get updates linked to this specific item (optional)
            project_id: Get all updates for this project (optional)
            limit: Maximum updates to return

        Returns:
            List of timeline entries for updates
        """
        entries = []

        with self.db._db_cursor(dictionary=True) as cursor:
            if item_id:
                # Get updates linked to specific item
                cursor.execute("""
                    SELECT u.id, u.content, u.created_at, ui.item_id
                    FROM updates u
                    JOIN update_items ui ON u.id = ui.update_id
                    WHERE ui.item_id = %s
                    ORDER BY u.created_at DESC
                    LIMIT %s
                """, (item_id, limit))
            elif project_id:
                # Get all updates for project
                cursor.execute("""
                    SELECT u.id, u.content, u.created_at,
                           GROUP_CONCAT(ui.item_id) as linked_items
                    FROM updates u
                    LEFT JOIN update_items ui ON u.id = ui.update_id
                    WHERE u.project_id = %s
                    GROUP BY u.id, u.content, u.created_at
                    ORDER BY u.created_at DESC
                    LIMIT %s
                """, (project_id, limit))
            else:
                return []

            updates = cursor.fetchall()

        for update in updates:
            # Truncate content for title
            content = update['content']
            truncated = content[:60] + '...' if len(content) > 60 else content

            entry = {
                'timestamp': update['created_at'],
                'activity_type': 'update',
                'item_id': update.get('item_id') or (
                    int(update['linked_items'].split(',')[0])
                    if update.get('linked_items') else None
                ),
                'title': f"Update: {truncated}",
                'details': {
                    'update_id': update['id'],
                    'content': content,
                    'linked_items': (
                        [int(x) for x in update['linked_items'].split(',')]
                        if update.get('linked_items') else []
                    )
                },
                'actor': None,
                'icon': ACTIVITY_ICONS['update'],
                'color': ACTIVITY_COLORS['update']
            }
            entries.append(entry)

        return entries

    def _get_commit_activities(self, item_id: int = None, project_wide: bool = False,
                               limit: int = 50) -> List[Dict[str, Any]]:
        """Get git commit activities.

        Args:
            item_id: Get commits for specific item (by message refs and linked files)
            project_wide: Get all project commits
            limit: Maximum commits to return

        Returns:
            List of timeline entries for commits
        """
        if not self.git_provider or not self.git_provider.is_valid():
            return []

        entries = []
        commits = []

        if project_wide:
            commits = self.git_provider.get_project_commits(limit=limit)
        elif item_id:
            # Get commits by message reference
            commits = self.git_provider.get_item_commits(item_id, limit=limit)

            # Also get commits for linked files
            linked_files = self.db.get_item_files(item_id)
            if linked_files:
                file_paths = [f['file_path'] for f in linked_files]
                file_commits = self.git_provider.get_commits_for_linked_files(file_paths, limit=limit)

                # Merge and dedupe
                seen_shas = {c['sha'] for c in commits}
                for fc in file_commits:
                    if fc['sha'] not in seen_shas:
                        fc['matched_via'] = 'linked_file'
                        commits.append(fc)
                        seen_shas.add(fc['sha'])

        for commit in commits:
            entry = {
                'timestamp': commit['timestamp'],
                'activity_type': 'commit',
                'item_id': item_id,
                'title': commit['summary'],
                'details': {
                    'sha': commit['sha'],
                    'sha_short': commit['sha_short'],
                    'message': commit['message'],
                    'author': commit['author'],
                    'author_email': commit.get('author_email'),
                    'files': commit.get('files', []),
                    'matched_ref': commit.get('matched_ref'),
                    'matched_via': commit.get('matched_via', 'message_ref')
                },
                'actor': commit['author'],
                'icon': ACTIVITY_ICONS['commit'],
                'color': ACTIVITY_COLORS['commit']
            }
            entries.append(entry)

        return entries

    def build_item_timeline(self, item_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        """Build unified timeline for a specific item.

        Aggregates:
        - Status changes
        - Decisions
        - Linked updates
        - Git commits (by message ref and linked files)

        Args:
            item_id: The item to build timeline for
            limit: Maximum entries to return

        Returns:
            List of timeline entries, sorted by timestamp descending
        """
        # Gather all activities
        activities = []
        activities.extend(self._get_status_activities(item_id))
        activities.extend(self._get_decision_activities(item_id))
        activities.extend(self._get_update_activities(item_id=item_id, limit=limit))
        activities.extend(self._get_commit_activities(item_id=item_id, limit=limit))

        # Sort by timestamp descending (most recent first)
        activities.sort(key=lambda x: x['timestamp'], reverse=True)

        return activities[:limit]

    def build_project_timeline(self, project_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Build unified timeline for an entire project.

        Aggregates:
        - All status changes for project items
        - All decisions for project items
        - All project updates
        - All git commits on current branch

        Args:
            project_id: The project to build timeline for
            limit: Maximum entries to return

        Returns:
            List of timeline entries, sorted by timestamp descending
        """
        activities = []

        # Get all items in project for status changes and decisions
        items = self.db.list_items(project_id=project_id, limit=500)
        for item in items:
            activities.extend(self._get_status_activities(item['id']))
            activities.extend(self._get_decision_activities(item['id']))

        # Get project updates
        activities.extend(self._get_update_activities(project_id=project_id, limit=limit))

        # Get project-wide commits
        activities.extend(self._get_commit_activities(project_wide=True, limit=limit))

        # Sort by timestamp descending (most recent first)
        activities.sort(key=lambda x: x['timestamp'], reverse=True)

        return activities[:limit]

    def serialize_timeline(self, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Serialize timeline entries for JSON output.

        Converts datetime objects to ISO format strings.

        Args:
            entries: List of timeline entries

        Returns:
            List of JSON-serializable timeline entries
        """
        serialized = []
        for entry in entries:
            serialized_entry = dict(entry)
            if isinstance(serialized_entry['timestamp'], datetime):
                serialized_entry['timestamp'] = serialized_entry['timestamp'].isoformat()
            serialized.append(serialized_entry)
        return serialized
