#!/usr/bin/env python3
"""Simple web UI for kanban-mcp."""

import os
import sys

from flask import Flask, render_template, request, jsonify, Response
from kanban_mcp.core import KanbanDB
from kanban_mcp.export import (
    ExportBuilder,
    export_to_format,
    get_mime_type,
    get_file_extension,
)

app = Flask(__name__)
db = None


def _get_db():
    """Lazy-init the database connection."""
    global db
    if db is None:
        db = KanbanDB()
    return db


@app.before_request
def _ensure_db():
    """Initialize DB on first request, not at import time."""
    _get_db()


# --- API Routes ---

@app.route('/api/items/<int:item_id>', methods=['GET'])
def api_get_item(item_id):
    """Get item details."""
    item = db.get_item(item_id)
    if not item:
        return jsonify({'error': 'Item not found'}), 404
    return jsonify({
        'id': item['id'],
        'title': item['title'],
        'description': item['description'],
        'priority': item['priority'],
        'complexity': item.get('complexity'),
        'type': item['type_name'],
        'status': item['status_name'],
        'parent_id': item.get('parent_id')
    })


@app.route('/api/items/<int:item_id>', methods=['DELETE'])
def api_delete_item(item_id):
    """Delete an item."""
    item = db.get_item(item_id)
    if not item:
        return jsonify({'success': False, 'error': 'Item not found'}), 404
    result = db.delete_item(item_id)
    return jsonify(result)


@app.route('/api/items/<int:item_id>', methods=['POST'])
def api_edit_item(item_id):
    """Edit item (title, description, priority, status)."""
    item = db.get_item(item_id)
    if not item:
        return jsonify({'success': False, 'error': 'Item not found'}), 404

    data = request.get_json() or {}

    # Handle status change separately (uses set_status with blocking logic)
    if 'status' in data:
        try:
            result = db.set_status(item_id, data['status'])
            if not result.get('success'):
                return jsonify(result), 400
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400

    # Handle other field updates
    update_fields = {}
    if 'title' in data:
        update_fields['title'] = data['title']
    if 'description' in data:
        update_fields['description'] = data['description']
    if 'priority' in data:
        update_fields['priority'] = data['priority']
    if 'complexity' in data:
        update_fields['complexity'] = data['complexity']

    if update_fields:
        result = db.update_item(item_id, **update_fields)
        if not result.get('success'):
            return jsonify(result), 400

    # Handle parent_id change separately
    if 'parent_id' in data:
        parent_val = (
            data['parent_id'] if data['parent_id']
            else None
        )
        parent_result = db.set_parent(
            item_id, parent_val
        )
        if not parent_result.get('success'):
            return jsonify(parent_result), 400

    return jsonify({'success': True})


@app.route('/api/items/<int:item_id>/status', methods=['POST'])
def api_set_status(item_id):
    """Set item status (for drag-drop)."""
    item = db.get_item(item_id)
    if not item:
        return jsonify({'success': False, 'error': 'Item not found'}), 404

    data = request.get_json() or {}
    status = data.get('status')
    if not status:
        return jsonify({'success': False, 'error': 'Status required'}), 400

    try:
        result = db.set_status(item_id, status)
        if not result.get('success'):
            return jsonify(result), 400
        return jsonify(result)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/export', methods=['GET'])
def api_export():
    """Export project data in various formats.

    Query params:
        project: Project ID (required)
        format: Output format - json, yaml, markdown (default: json)
        type: Filter by item type
        status: Filter by status
        ids: Comma-separated item IDs
        tags: Include tags (default: true)
        relationships: Include relationships (default: false)
        metrics: Include metrics (default: false)
        updates: Include updates (default: false)
        epic_progress: Include epic progress (default: false)
        detailed: For markdown, show detailed view (default: false)
        limit: Max items (default: 500)
        download: If true, set Content-Disposition header (default: false)
    """
    project_id = request.args.get('project', '')
    if not project_id:
        return jsonify({'error': 'project parameter required'}), 400

    # Get format
    format_type = request.args.get('format', 'json').lower()
    if format_type not in ('json', 'yaml', 'markdown', 'md'):
        return jsonify({
            'error': 'Invalid format.'
            ' Use json, yaml, or markdown'
        }), 400

    # Parse filter parameters
    item_type = request.args.get('type', '') or None
    status = request.args.get('status', '') or None

    # Parse item IDs
    ids_param = request.args.get('ids', '')
    item_ids = None
    if ids_param:
        try:
            item_ids = [
                int(x.strip())
                for x in ids_param.split(',')
                if x.strip()
            ]
        except ValueError:
            return jsonify({'error': 'Invalid item IDs'}), 400

    # Parse boolean options
    def parse_bool(param, default=False):
        val = request.args.get(param, '').lower()
        if val in ('true', '1', 'yes'):
            return True
        if val in ('false', '0', 'no'):
            return False
        return default

    include_tags = parse_bool('tags', True)
    include_relationships = parse_bool('relationships', False)
    include_metrics = parse_bool('metrics', False)
    include_updates = parse_bool('updates', False)
    include_epic_progress = parse_bool('epic_progress', False)
    detailed = parse_bool('detailed', False)
    download = parse_bool('download', False)

    # Parse limit
    try:
        limit = int(request.args.get('limit', '500'))
        limit = max(1, min(limit, 10000))  # Clamp to reasonable range
    except ValueError:
        limit = 500

    try:
        # Build export data
        builder = ExportBuilder(db, project_id)
        data = builder.build_export_data(
            item_ids=item_ids,
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
        content = export_to_format(data, format=format_type, detailed=detailed)

        # Build response
        mime_type = get_mime_type(format_type)
        response = Response(content, mimetype=mime_type)

        # Set download header if requested
        if download:
            project = db.get_project_by_id(project_id)
            project_name = project['name'] if project else 'export'
            # Sanitize filename
            safe_name = ''.join(
                c for c in project_name
                if c.isalnum() or c in '-_'
            )[:50]
            ext = get_file_extension(format_type)
            response.headers['Content-Disposition'] = (
                f'attachment; filename="{safe_name}{ext}"'
            )

        return response

    except ImportError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/items', methods=['POST'])
def api_create_item():
    """Create a new item."""
    data = request.get_json() or {}

    project_id = data.get('project_id')
    item_type = data.get('type')
    title = data.get('title')
    description = data.get('description', '')
    priority = data.get('priority', 3)
    complexity = data.get('complexity')
    parent_id = data.get('parent_id')

    if not project_id or not item_type or not title:
        return jsonify({
            'success': False,
            'error': (
                'project_id, type,'
                ' and title required'
            ),
        }), 400

    try:
        item_id = db.create_item(
            project_id, item_type, title,
            description, priority, complexity,
            parent_id=parent_id,
        )
        return jsonify({
            'success': True, 'item_id': item_id
        }), 201
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/items', methods=['GET'])
def api_list_items():
    """List items for a project (for dropdown selection)."""
    project_id = request.args.get('project', '')
    if not project_id:
        return jsonify({'items': []})

    with db._db_cursor(dictionary=True) as cursor:
        cursor.execute(db._sql("""
            SELECT i.id, i.title, t.name as type, s.name as status
            FROM items i
            JOIN item_types t ON i.type_id = t.id
            JOIN statuses s ON i.status_id = s.id
            WHERE i.project_id = %s
            ORDER BY i.id DESC
        """), (project_id,))
        items = cursor.fetchall()

    return jsonify({'items': items})


@app.route('/api/updates', methods=['POST'])
def api_create_update():
    """Create a new update, optionally linked to items."""
    data = request.get_json() or {}

    project_id = data.get('project_id')
    content = data.get('content')
    item_ids = data.get('item_ids', [])

    if not project_id:
        return jsonify({'success': False, 'error': 'project_id required'}), 400
    if not content:
        return jsonify({'success': False, 'error': 'content required'}), 400

    update_id = db.add_update(
        project_id, content,
        item_ids if item_ids else None,
    )
    return jsonify({'success': True, 'update_id': update_id}), 201


@app.route('/api/projects/<project_id>', methods=['DELETE'])
def api_delete_project(project_id):
    """Delete a project and all its data."""
    with db._db_cursor(dictionary=True, commit=True) as cursor:
        # Check project exists
        cursor.execute(
            db._sql("SELECT id FROM projects WHERE id = %s"),
            (project_id,))
        if not cursor.fetchone():
            return jsonify({
                'success': False,
                'error': 'Project not found',
            }), 404

        # Clean up embeddings (no FK to projects, must delete manually)
        cursor.execute(db._sql("""
            DELETE FROM embeddings WHERE source_type = 'item'
            AND source_id IN (SELECT id FROM items WHERE project_id = %s)
        """), (project_id,))
        cursor.execute(db._sql("""
            DELETE FROM embeddings
            WHERE source_type = 'decision'
            AND source_id IN (
                SELECT id FROM item_decisions
                WHERE item_id IN (
                    SELECT id FROM items
                    WHERE project_id = %s
                )
            )
        """), (project_id,))
        cursor.execute(db._sql("""
            DELETE FROM embeddings WHERE source_type = 'update'
            AND source_id IN (SELECT id FROM updates WHERE project_id = %s)
        """), (project_id,))

        # CASCADE handles items, updates, tags, relationships, etc.
        cursor.execute(
            db._sql("DELETE FROM projects WHERE id = %s"),
            (project_id,))

    return jsonify({'success': True})


# --- Tag API Routes ---

@app.route('/api/tags', methods=['GET'])
def api_list_tags():
    """Get all tags for a project."""
    project_id = request.args.get('project', '')
    if not project_id:
        return jsonify({'tags': []})
    tags = db.get_project_tags(project_id)
    return jsonify({'tags': tags})


@app.route('/api/tags', methods=['POST'])
def api_create_tag():
    """Create or get a tag."""
    data = request.get_json() or {}
    project_id = data.get('project_id')
    name = data.get('name')
    color = data.get('color')

    if not project_id or not name:
        return jsonify({
            'success': False,
            'error': 'project_id and name required',
        }), 400

    try:
        tag_id = db.ensure_tag(project_id, name, color)
        tag = db.get_tag(tag_id)
        return jsonify({'success': True, 'tag': tag}), 201
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/tags/<int:tag_id>', methods=['POST'])
def api_update_tag(tag_id):
    """Update tag name/color."""
    data = request.get_json() or {}
    result = db.update_tag(tag_id, data.get('name'), data.get('color'))

    if not result.get('success'):
        return jsonify(result), 400
    return jsonify(result)


@app.route('/api/tags/<int:tag_id>', methods=['DELETE'])
def api_delete_tag(tag_id):
    """Delete a tag."""
    result = db.delete_tag(tag_id)
    return jsonify(result)


@app.route('/api/epics', methods=['GET'])
def api_list_epics():
    """Get all epics for a project (for parent selector dropdown)."""
    project_id = request.args.get('project', '')
    if not project_id:
        return jsonify({'epics': []})

    items = db.list_items(project_id=project_id, type_name='epic', limit=100)
    epics = [
        {
            'id': item['id'],
            'title': item['title'],
            'status': item['status_name'],
        }
        for item in items
    ]
    return jsonify({'epics': epics})


@app.route('/api/items/<int:item_id>/children', methods=['GET'])
def api_get_item_children(item_id):
    """Get children of an item."""
    children = db.get_children(item_id)
    return jsonify({'children': children})


@app.route('/api/search', methods=['GET'])
def api_search():
    """Full-text search across items and updates."""
    project_id = request.args.get('project', '')
    query = request.args.get('q', '')

    if not project_id:
        return jsonify({'error': 'project parameter required'}), 400
    if not query:
        return jsonify({'items': [], 'updates': [], 'total_count': 0})

    try:
        limit = int(request.args.get('limit', '20'))
        limit = max(1, min(limit, 100))
    except ValueError:
        limit = 20

    results = db.search(project_id, query, limit)
    return jsonify(results)


@app.route('/api/semantic-search', methods=['GET'])
def api_semantic_search():
    """Semantic search across items, decisions, and updates.

    Query params:
        project: Project ID (required)
        q: Search query (required)
        limit: Max results (default: 10)
        types: Comma-separated source types
            (item,decision,update). Empty = all
        threshold: Minimum similarity 0.0-1.0 (default: 0.0)
    """
    project_id = request.args.get('project', '')
    query = request.args.get('q', '')

    if not project_id:
        return jsonify({'error': 'project parameter required'}), 400
    if not query:
        return jsonify({'results': [], 'total_count': 0})

    try:
        limit = int(request.args.get('limit', '10'))
        limit = max(1, min(limit, 100))
    except ValueError:
        limit = 10

    try:
        threshold = float(request.args.get('threshold', '0.0'))
        threshold = max(0.0, min(threshold, 1.0))
    except ValueError:
        threshold = 0.0

    types_param = request.args.get('types', '')
    source_types = (
        [
            t.strip()
            for t in types_param.split(',')
            if t.strip()
        ]
        if types_param
        else None
    )

    try:
        results = db.semantic_search(
            project_id=project_id,
            query=query,
            limit=limit,
            source_types=source_types,
            threshold=threshold
        )
        return jsonify({
            'results': results,
            'total_count': len(results)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/items/<int:item_id>/tags', methods=['GET'])
def api_get_item_tags(item_id):
    """Get tags for an item."""
    tags = db.get_item_tags(item_id)
    return jsonify({'tags': tags})


@app.route('/api/items/<int:item_id>/tags', methods=['POST'])
def api_add_item_tags(item_id):
    """Add tags to an item."""
    data = request.get_json() or {}
    tag_names = data.get('tags', [])

    if not tag_names:
        return jsonify({'success': False, 'error': 'tags required'}), 400

    results = []
    for tag_name in tag_names:
        try:
            result = db.add_tag_to_item(item_id, tag_name)
            results.append(result)
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400

    return jsonify({
        'success': True,
        'results': results,
        'tags': db.get_item_tags(item_id),
    })


@app.route('/api/items/<int:item_id>/tags/<int:tag_id>', methods=['DELETE'])
def api_remove_item_tag(item_id, tag_id):
    """Remove a tag from an item."""
    result = db.remove_tag_from_item(item_id, tag_id)
    return jsonify(result)


# --- File Linking API Routes ---

@app.route('/api/items/<int:item_id>/files', methods=['GET'])
def api_get_item_files(item_id):
    """Get files linked to an item."""
    files = db.get_item_files(item_id)
    return jsonify({'files': files})


@app.route('/api/items/<int:item_id>/files', methods=['POST'])
def api_link_file(item_id):
    """Link a file to an item."""
    data = request.get_json() or {}
    file_path = data.get('file_path')
    line_start = data.get('line_start')
    line_end = data.get('line_end')

    if not file_path:
        return jsonify({'success': False, 'error': 'file_path required'}), 400

    try:
        result = db.link_file(item_id, file_path, line_start, line_end)
        if not result.get('success'):
            return jsonify(result), 400
        return jsonify(result), 201
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/items/<int:item_id>/files', methods=['DELETE'])
def api_unlink_file(item_id):
    """Unlink a file from an item."""
    data = request.get_json() or {}
    file_path = data.get('file_path')
    line_start = data.get('line_start')
    line_end = data.get('line_end')

    if not file_path:
        return jsonify({'success': False, 'error': 'file_path required'}), 400

    result = db.unlink_file(item_id, file_path, line_start, line_end)
    return jsonify(result)


# --- Decision History API Routes ---

@app.route('/api/items/<int:item_id>/decisions', methods=['GET'])
def api_get_item_decisions(item_id):
    """Get decisions for an item."""
    decisions = db.get_item_decisions(item_id)
    return jsonify({'decisions': decisions})


@app.route('/api/items/<int:item_id>/decisions', methods=['POST'])
def api_add_decision(item_id):
    """Add a decision to an item."""
    data = request.get_json() or {}
    choice = data.get('choice')
    rejected_alternatives = data.get('rejected_alternatives')
    rationale = data.get('rationale')

    if not choice:
        return jsonify({'success': False, 'error': 'choice required'}), 400

    try:
        result = db.add_decision(
            item_id, choice,
            rejected_alternatives, rationale,
        )
        if not result.get('success'):
            return jsonify(result), 400
        return jsonify(result), 201
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/decisions/<int:decision_id>', methods=['DELETE'])
def api_delete_decision(decision_id):
    """Delete a decision."""
    result = db.delete_decision(decision_id)
    return jsonify(result)


# --- Timeline API Routes ---

@app.route('/api/items/<int:item_id>/timeline')
def api_get_item_timeline(item_id):
    """Get activity timeline for an item.

    Query params:
        limit: Maximum entries (default: 100)
    """
    try:
        limit = int(request.args.get('limit', '100'))
        limit = max(1, min(limit, 500))
    except ValueError:
        limit = 100

    # Get project directory for git integration
    item = db.get_item(item_id)
    if not item:
        return jsonify({'error': 'Item not found'}), 404

    project = db.get_project_by_id(item['project_id'])
    repo_path = project.get('directory_path') if project else None

    result = db.get_timeline_data(
        item_id=item_id, limit=limit,
        repo_path=repo_path,
    )
    return jsonify(result)


@app.route('/api/projects/<project_id>/timeline')
def api_get_project_timeline(project_id):
    """Get activity timeline for a project.

    Query params:
        limit: Maximum entries (default: 100)
    """
    try:
        limit = int(request.args.get('limit', '100'))
        limit = max(1, min(limit, 500))
    except ValueError:
        limit = 100

    project = db.get_project_by_id(project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404

    repo_path = project.get('directory_path')

    result = db.get_timeline_data(
        project_id=project_id, limit=limit,
        repo_path=repo_path,
    )
    return jsonify(result)


STATUSES = ['backlog', 'todo', 'in_progress', 'review', 'done', 'closed']


def get_all_relationships(project_id):
    """Get relationships for all items in a project, organized by item."""
    relationships = {}

    with db._db_cursor(dictionary=True) as cursor:
        # Get all relationships where source or target is in this project
        # Include statuses so we can determine if blockers are resolved
        cursor.execute(db._sql("""
            SELECT r.source_item_id, r.target_item_id, r.relationship_type,
                   si.title as source_title, ti.title as target_title,
                   ss.name as source_status, ts.name as target_status
            FROM item_relationships r
            JOIN items si ON r.source_item_id = si.id
            JOIN items ti ON r.target_item_id = ti.id
            JOIN statuses ss ON si.status_id = ss.id
            JOIN statuses ts ON ti.status_id = ts.id
            WHERE si.project_id = %s OR ti.project_id = %s
        """), (project_id, project_id))

        for rel in cursor.fetchall():
            src_id = rel['source_item_id']
            tgt_id = rel['target_item_id']
            rel_type = rel['relationship_type']

            # Initialize if needed
            if src_id not in relationships:
                relationships[src_id] = {
                    'blocked_by': [],
                    'blocks': [],
                    'depends_on': [],
                    'dependency_of': [],
                    'relates_to': [],
                    'duplicates': [],
                }
            if tgt_id not in relationships:
                relationships[tgt_id] = {
                    'blocked_by': [],
                    'blocks': [],
                    'depends_on': [],
                    'dependency_of': [],
                    'relates_to': [],
                    'duplicates': [],
                }

            if rel_type == 'blocks':
                relationships[src_id]['blocks'].append({
                    'id': tgt_id,
                    'title': rel['target_title'],
                })
                relationships[tgt_id][
                    'blocked_by'
                ].append({
                    'id': src_id,
                    'title': rel['source_title'],
                    'status': rel['source_status'],
                })
            elif rel_type == 'depends_on':
                relationships[src_id][
                    'depends_on'
                ].append({
                    'id': tgt_id,
                    'title': rel['target_title'],
                })
                relationships[tgt_id][
                    'dependency_of'
                ].append({
                    'id': src_id,
                    'title': rel['source_title'],
                })
            elif rel_type == 'relates_to':
                relationships[src_id][
                    'relates_to'
                ].append({
                    'id': tgt_id,
                    'title': rel['target_title'],
                })
                relationships[tgt_id][
                    'relates_to'
                ].append({
                    'id': src_id,
                    'title': rel['source_title'],
                })
            elif rel_type == 'duplicates':
                relationships[src_id][
                    'duplicates'
                ].append({
                    'id': tgt_id,
                    'title': rel['target_title'],
                })
                relationships[tgt_id][
                    'duplicates'
                ].append({
                    'id': src_id,
                    'title': rel['source_title'],
                })

    return relationships


@app.route('/')
def index():
    # Get all projects
    with db._db_cursor(dictionary=True) as cursor:
        cursor.execute(
            "SELECT id, name, directory_path"
            " FROM projects ORDER BY name"
        )
        projects = cursor.fetchall()

    current_project = request.args.get('project', '')
    items_by_status = {}
    relationships = {}

    epic_progress = {}

    if current_project:
        with db._db_cursor(dictionary=True) as cursor:
            # Get items
            cursor.execute(db._sql("""
                SELECT i.id, i.title, i.description, i.priority, i.complexity,
                       i.parent_id, t.name as type, s.name as status
                FROM items i
                JOIN item_types t ON i.type_id = t.id
                JOIN statuses s ON i.status_id = s.id
                WHERE i.project_id = %s
                ORDER BY i.priority, i.id
            """), (current_project,))
            items = cursor.fetchall()

            # Get tags for all items in one query
            item_ids = [item['id'] for item in items]
            item_tags = {}
            if item_ids:
                placeholders = ','.join(
                    [db._backend.placeholder] * len(item_ids))
                cursor.execute(f"""
                    SELECT it.item_id, t.id, t.name, t.color
                    FROM item_tags it
                    JOIN tags t ON it.tag_id = t.id
                    WHERE it.item_id IN ({placeholders})
                    ORDER BY t.name
                """, tuple(item_ids))  # nosec B608
                for row in cursor.fetchall():
                    if row['item_id'] not in item_tags:
                        item_tags[row['item_id']] = []
                    item_tags[row['item_id']].append({
                        'id': row['id'],
                        'name': row['name'],
                        'color': row['color']
                    })

            for item in items:
                item['tags'] = item_tags.get(item['id'], [])
                status = item['status']
                if status not in items_by_status:
                    items_by_status[status] = []
                items_by_status[status].append(item)

                # Calculate progress for epic items
                if item['type'] == 'epic':
                    epic_progress[item['id']] = (
                        db.get_epic_progress(item['id'])
                    )

        # Get relationships
        relationships = get_all_relationships(current_project)

    # Get current project directory path
    current_project_dir = ''
    if current_project:
        for p in projects:
            if p['id'] == current_project:
                current_project_dir = p['directory_path']
                break

    return render_template(
        'index.html',
        projects=projects,
        current_project=current_project,
        current_project_dir=current_project_dir,
        statuses=STATUSES,
        items_by_status=items_by_status,
        relationships=relationships,
        epic_progress=epic_progress
    )


def _run_with_gunicorn(host, port):
    """Run with gunicorn (Unix only)."""
    from gunicorn.app.base import BaseApplication

    class KanbanGunicorn(BaseApplication):
        def __init__(self, flask_app, options=None):
            self.flask_app = flask_app
            self.options = options or {}
            super().__init__()

        def load_config(self):
            for key, value in self.options.items():
                self.cfg.set(key.lower(), value)

        def load(self):
            return self.flask_app

    options = {
        'bind': f'{host}:{port}',
        'workers': 1,
        'worker_class': 'gthread',
        'threads': 4,
        'preload_app': True,
        'accesslog': '-',
    }
    KanbanGunicorn(app, options).run()


def _run_with_waitress(host, port):
    """Run with waitress (cross-platform)."""
    from waitress import serve
    serve(app, host=host, port=port)


def main():
    """Main entry point for kanban-web console script."""
    import argparse
    parser = argparse.ArgumentParser(description='Kanban web UI')
    parser.add_argument(
        '--port', '-p', type=int,
        default=int(os.environ.get("KANBAN_WEB_PORT", "5000")),
        help='Port to run on (env: KANBAN_WEB_PORT)',
    )
    parser.add_argument(
        '--host', '-H',
        default=os.environ.get("KANBAN_WEB_HOST", "127.0.0.1"),
        help='Host to bind to (env: KANBAN_WEB_HOST)',
    )
    parser.add_argument(
        '--debug', '-d', action='store_true',
        help='Debug mode',
    )
    args = parser.parse_args()

    if args.host in ('0.0.0.0', '::'):
        print(
            f"WARNING: Binding to {args.host}"
            " exposes this server to the"
            " network. There is no"
            " authentication — anyone on your"
            " network can read/modify data.",
            file=sys.stderr,
        )
    if args.debug:
        print(
            f"Starting kanban web UI on"
            f" http://{args.host}:{args.port}"
            f" (debug mode, Flask dev server)"
        )
        app.run(
            host=args.host, port=args.port,
            use_reloader=True,
        )
        return

    print(
        f"Starting kanban web UI on"
        f" http://{args.host}:{args.port}"
    )
    try:
        import gunicorn  # noqa: F401
        print("Using gunicorn")
        _run_with_gunicorn(args.host, args.port)
    except ImportError:
        try:
            import waitress  # noqa: F401
            print("Using waitress")
            _run_with_waitress(args.host, args.port)
        except ImportError:
            print(
                "WARNING: No production WSGI"
                " server found. Using Flask"
                " dev server.\n"
                "Install waitress with:"
                " pip install waitress",
                file=sys.stderr
            )
            app.run(host=args.host, port=args.port)


if __name__ == '__main__':
    main()
