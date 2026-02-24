#!/usr/bin/env python3
"""Simple web UI for kanban-mcp."""

import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, render_template, request, jsonify
from kanban_mcp import KanbanDB

app = Flask(__name__)
db = KanbanDB()


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
        'status': item['status_name']
    })


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

    if not project_id or not item_type or not title:
        return jsonify({'success': False, 'error': 'project_id, type, and title required'}), 400

    try:
        item_id = db.create_item(project_id, item_type, title, description, priority, complexity)
        return jsonify({'success': True, 'item_id': item_id}), 201
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/items', methods=['GET'])
def api_list_items():
    """List items for a project (for dropdown selection)."""
    project_id = request.args.get('project', '')
    if not project_id:
        return jsonify({'items': []})

    with db._get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT i.id, i.title, t.name as type, s.name as status
            FROM items i
            JOIN item_types t ON i.type_id = t.id
            JOIN statuses s ON i.status_id = s.id
            WHERE i.project_id = %s
            ORDER BY i.id DESC
        """, (project_id,))
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

    update_id = db.add_update(project_id, content, item_ids if item_ids else None)
    return jsonify({'success': True, 'update_id': update_id}), 201


@app.route('/api/projects/<project_id>', methods=['DELETE'])
def api_delete_project(project_id):
    """Delete a project and all its data."""
    with db._get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        try:
            # Check project exists
            cursor.execute("SELECT id FROM projects WHERE id = %s", (project_id,))
            if not cursor.fetchone():
                return jsonify({'success': False, 'error': 'Project not found'}), 404

            # Delete in order respecting foreign keys (all in same transaction)
            cursor.execute("""
                DELETE FROM update_items
                WHERE update_id IN (SELECT id FROM updates WHERE project_id = %s)
            """, (project_id,))
            cursor.execute("DELETE FROM updates WHERE project_id = %s", (project_id,))
            cursor.execute("""
                DELETE FROM item_tags
                WHERE item_id IN (SELECT id FROM items WHERE project_id = %s)
            """, (project_id,))
            cursor.execute("""
                DELETE FROM item_relationships
                WHERE source_item_id IN (SELECT id FROM items WHERE project_id = %s)
                   OR target_item_id IN (SELECT id FROM items WHERE project_id = %s)
            """, (project_id, project_id))
            cursor.execute("""
                DELETE FROM status_history
                WHERE item_id IN (SELECT id FROM items WHERE project_id = %s)
            """, (project_id,))
            cursor.execute("DELETE FROM items WHERE project_id = %s", (project_id,))
            cursor.execute("DELETE FROM tags WHERE project_id = %s", (project_id,))
            cursor.execute("DELETE FROM projects WHERE id = %s", (project_id,))
            conn.commit()
        except Exception as e:
            conn.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500

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
        return jsonify({'success': False, 'error': 'project_id and name required'}), 400

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

    return jsonify({'success': True, 'results': results, 'tags': db.get_item_tags(item_id)})


@app.route('/api/items/<int:item_id>/tags/<int:tag_id>', methods=['DELETE'])
def api_remove_item_tag(item_id, tag_id):
    """Remove a tag from an item."""
    result = db.remove_tag_from_item(item_id, tag_id)
    return jsonify(result)



STATUSES = ['backlog', 'todo', 'in_progress', 'review', 'done', 'closed']

def get_all_relationships(project_id):
    """Get relationships for all items in a project, organized by item."""
    relationships = {}
    
    with db._get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        
        # Get all relationships where source or target is in this project
        cursor.execute("""
            SELECT r.source_item_id, r.target_item_id, r.relationship_type,
                   si.title as source_title, ti.title as target_title
            FROM item_relationships r
            JOIN items si ON r.source_item_id = si.id
            JOIN items ti ON r.target_item_id = ti.id
            WHERE si.project_id = %s OR ti.project_id = %s
        """, (project_id, project_id))
        
        for rel in cursor.fetchall():
            src_id = rel['source_item_id']
            tgt_id = rel['target_item_id']
            rel_type = rel['relationship_type']
            
            # Initialize if needed
            if src_id not in relationships:
                relationships[src_id] = {'blocked_by': [], 'blocks': [], 'depends_on': [], 'dependency_of': [], 'relates_to': [], 'duplicates': []}
            if tgt_id not in relationships:
                relationships[tgt_id] = {'blocked_by': [], 'blocks': [], 'depends_on': [], 'dependency_of': [], 'relates_to': [], 'duplicates': []}
            
            if rel_type == 'blocks':
                # source blocks target
                relationships[src_id]['blocks'].append({'id': tgt_id, 'title': rel['target_title']})
                relationships[tgt_id]['blocked_by'].append({'id': src_id, 'title': rel['source_title']})
            elif rel_type == 'depends_on':
                # source depends on target
                relationships[src_id]['depends_on'].append({'id': tgt_id, 'title': rel['target_title']})
                relationships[tgt_id]['dependency_of'].append({'id': src_id, 'title': rel['source_title']})
            elif rel_type == 'relates_to':
                # symmetric
                relationships[src_id]['relates_to'].append({'id': tgt_id, 'title': rel['target_title']})
                relationships[tgt_id]['relates_to'].append({'id': src_id, 'title': rel['source_title']})
            elif rel_type == 'duplicates':
                # symmetric
                relationships[src_id]['duplicates'].append({'id': tgt_id, 'title': rel['target_title']})
                relationships[tgt_id]['duplicates'].append({'id': src_id, 'title': rel['source_title']})
    
    return relationships

@app.route('/')
def index():
    # Get all projects
    with db._get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, name, directory_path FROM projects ORDER BY name")
        projects = cursor.fetchall()
    
    current_project = request.args.get('project', '')
    items_by_status = {}
    updates_by_item = {}
    relationships = {}
    
    if current_project:
        with db._get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            
            # Get items
            cursor.execute("""
                SELECT i.id, i.title, i.description, i.priority, i.complexity,
                       t.name as type, s.name as status
                FROM items i
                JOIN item_types t ON i.type_id = t.id
                JOIN statuses s ON i.status_id = s.id
                WHERE i.project_id = %s
                ORDER BY i.priority, i.id
            """, (current_project,))
            items = cursor.fetchall()
            
            # Get tags for all items in one query
            item_ids = [item['id'] for item in items]
            item_tags = {}
            if item_ids:
                placeholders = ','.join(['%s'] * len(item_ids))
                cursor.execute(f"""
                    SELECT it.item_id, t.id, t.name, t.color
                    FROM item_tags it
                    JOIN tags t ON it.tag_id = t.id
                    WHERE it.item_id IN ({placeholders})
                    ORDER BY t.name
                """, tuple(item_ids))
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

            # Get updates with their linked items
            cursor.execute("""
                SELECT u.id, u.content, u.created_at, ui.item_id
                FROM updates u
                LEFT JOIN update_items ui ON u.id = ui.update_id
                WHERE u.project_id = %s
                ORDER BY u.created_at DESC
                LIMIT 50
            """, (current_project,))
            updates = cursor.fetchall()
            
            # Group updates by item
            for update in updates:
                item_id = update['item_id'] or 'general'
                if item_id not in updates_by_item:
                    # Get item info if linked
                    item_info = None
                    if item_id != 'general':
                        cursor.execute("SELECT id, title FROM items WHERE id = %s", (item_id,))
                        item_info = cursor.fetchone()
                    updates_by_item[item_id] = {'item': item_info, 'updates': []}
                updates_by_item[item_id]['updates'].append(update)
        
        # Get relationships
        relationships = get_all_relationships(current_project)
    
    return render_template(
        'index.html',
        projects=projects,
        current_project=current_project,
        statuses=STATUSES,
        items_by_status=items_by_status,
        updates_by_item=updates_by_item,
        relationships=relationships
    )

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Kanban web UI')
    parser.add_argument('--port', '-p', type=int, default=5000, help='Port to run on')
    parser.add_argument('--host', '-H', default='127.0.0.1', help='Host to bind to')
    parser.add_argument('--debug', '-d', action='store_true', help='Debug mode')
    args = parser.parse_args()
    
    print(f"Starting kanban web UI on http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug)
