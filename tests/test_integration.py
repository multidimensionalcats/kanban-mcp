#!/usr/bin/env python3
"""
Parametrized integration tests — run against all available backends.

Uses the `db` fixture from conftest.py, which is parametrized
across SQLite (always) and MySQL (when available).
"""


# ===================================================================
# Core CRUD
# ===================================================================


class TestCRUD:
    def test_ensure_project_creates_project(self, db):
        pid = db.ensure_project("/tmp/int-test", "Integration")
        assert pid is not None
        assert len(pid) == 16

    def test_ensure_project_idempotent(self, db):
        pid1 = db.ensure_project("/tmp/idem-test", "Idem")
        pid2 = db.ensure_project("/tmp/idem-test", "Idem")
        assert pid1 == pid2

    def test_create_item_returns_id(self, db, project_id):
        item_id = db.create_item(
            project_id, 'issue', 'Bug Title', 'desc', 3)
        assert isinstance(item_id, int)
        assert item_id > 0

    def test_get_item_returns_all_fields(self, db, project_id):
        item_id = db.create_item(
            project_id, 'feature', 'My Feature', 'details', 2)
        item = db.get_item(item_id)
        assert item is not None
        assert item['title'] == 'My Feature'
        assert item['description'] == 'details'
        assert item['priority'] == 2
        assert 'type_name' in item
        assert 'status_name' in item
        assert item['type_name'] == 'feature'

    def test_list_items_filters_by_type(self, db, project_id):
        db.create_item(project_id, 'issue', 'Issue 1', '', 3)
        db.create_item(project_id, 'todo', 'Todo 1', '', 3)
        items = db.list_items(project_id, type_name='issue')
        assert all(i['type_name'] == 'issue' for i in items)

    def test_list_items_filters_by_status(self, db, project_id):
        db.create_item(project_id, 'issue', 'Item 1', '', 3)
        items = db.list_items(
            project_id, status_name='backlog')
        assert len(items) >= 1
        assert all(i['status_name'] == 'backlog' for i in items)

    def test_list_items_filters_by_tags(self, db, project_id):
        item_id = db.create_item(
            project_id, 'issue', 'Tagged', '', 3)
        db.add_tag_to_item(item_id, 'urgent')
        items = db.list_items(
            project_id, tag_names=['urgent'])
        assert len(items) >= 1
        assert any(i['id'] == item_id for i in items)

    def test_edit_item_updates_fields(self, db, project_id):
        item_id = db.create_item(
            project_id, 'issue', 'Original', 'old', 3)
        result = db.update_item(
            item_id, title='Updated', description='new')
        assert result['success'] is True
        item = db.get_item(item_id)
        assert item['title'] == 'Updated'
        assert item['description'] == 'new'

    def test_delete_item(self, db, project_id):
        item_id = db.create_item(
            project_id, 'todo', 'To Delete', '', 3)
        result = db.delete_item(item_id)
        assert result['success'] is True
        assert db.get_item(item_id) is None


# ===================================================================
# Status workflow
# ===================================================================

class TestStatusWorkflow:
    def test_advance_status_follows_workflow(self, db, project_id):
        item_id = db.create_item(
            project_id, 'issue', 'Advancing', '', 3)
        result = db.advance_status(item_id)
        assert result['success'] is True
        assert result['new_status'] == 'todo'

    def test_advance_status_rejects_invalid_transition(
            self, db, project_id):
        # Diary items start at 'done' — can't advance further
        item_id = db.create_item(
            project_id, 'diary', 'Entry', 'Content', 3)
        result = db.advance_status(item_id)
        assert result['success'] is False

    def test_revert_status(self, db, project_id):
        item_id = db.create_item(
            project_id, 'issue', 'Reverting', '', 3)
        db.advance_status(item_id)  # backlog -> todo
        result = db.revert_status(item_id)
        assert result['success'] is True
        assert result['new_status'] == 'backlog'

    def test_set_status_arbitrary(self, db, project_id):
        item_id = db.create_item(
            project_id, 'issue', 'Set Status', '', 3)
        result = db.set_status(item_id, 'in_progress')
        assert result['success'] is True
        assert result['new_status'] == 'in_progress'

    def test_close_item_sets_closed_at(self, db, project_id):
        item_id = db.create_item(
            project_id, 'issue', 'To Close', '', 3)
        result = db.close_item(item_id)
        assert result['success'] is True
        item = db.get_item(item_id)
        assert item['closed_at'] is not None

    def test_close_item_closed_at_is_valid_timestamp(
            self, db, project_id):
        from datetime import datetime
        item_id = db.create_item(
            project_id, 'issue', 'Timestamp Test', '', 3)
        db.close_item(item_id)
        item = db.get_item(item_id)
        closed_at = item['closed_at']
        # Should be parseable as a timestamp
        if isinstance(closed_at, str):
            # SQLite returns strings
            dt = datetime.fromisoformat(closed_at)
        else:
            # MySQL returns datetime objects
            dt = closed_at
        assert dt.year >= 2024


# ===================================================================
# Updates
# ===================================================================

class TestUpdates:
    def test_add_update_with_linked_items(self, db, project_id):
        item_id = db.create_item(
            project_id, 'issue', 'Updated', '', 3)
        update_id = db.add_update(
            project_id, 'Progress note', [item_id])
        assert isinstance(update_id, int)
        assert update_id > 0

    def test_get_latest_update_parses_item_ids(
            self, db, project_id):
        item_id = db.create_item(
            project_id, 'issue', 'Latest', '', 3)
        db.add_update(
            project_id, 'Latest update', [item_id])
        update = db.get_latest_update(project_id)
        assert update is not None
        assert 'item_ids' in update

    def test_get_updates_multiple_items_linked(
            self, db, project_id):
        id1 = db.create_item(
            project_id, 'issue', 'Item A', '', 3)
        id2 = db.create_item(
            project_id, 'issue', 'Item B', '', 3)
        db.add_update(
            project_id, 'Multi update', [id1, id2])
        updates = db.get_updates(project_id)
        assert len(updates) >= 1
        # The latest update should reference both items
        latest = updates[0]
        assert 'item_ids' in latest


# ===================================================================
# Search
# ===================================================================

class TestSearch:
    def test_search_finds_by_title(self, db, project_id):
        db.create_item(
            project_id, 'issue', 'Unique Searchable Bug', '', 3)
        results = db.search(project_id, 'Searchable', limit=10)
        assert results['total_count'] >= 1

    def test_search_finds_by_description(self, db, project_id):
        db.create_item(
            project_id, 'issue', 'Generic',
            'findable_unique_description', 3)
        results = db.search(
            project_id, 'findable_unique', limit=10)
        assert results['total_count'] >= 1

    def test_search_finds_updates_by_content(self, db, project_id):
        db.add_update(
            project_id, 'searchable_update_content_xyz', [])
        results = db.search(
            project_id, 'searchable_update_content', limit=10)
        assert results['total_count'] >= 1

    def test_search_case_insensitive(self, db, project_id):
        db.create_item(
            project_id, 'issue', 'CaseTest', '', 3)
        results = db.search(project_id, 'casetest', limit=10)
        # LIKE is case-insensitive by default in SQLite and MySQL
        assert results['total_count'] >= 1

    def test_search_respects_project_scope(self, db, project_id):
        other_pid = db.ensure_project(
            "/tmp/other-proj", "Other")
        db.create_item(
            other_pid, 'issue',
            'unique_other_project_item_xyz', '', 3)
        results = db.search(
            project_id, 'unique_other_project_item_xyz',
            limit=10)
        assert results['total_count'] == 0

    def test_search_returns_correct_structure(self, db, project_id):
        results = db.search(project_id, 'anything', limit=10)
        assert 'items' in results
        assert 'updates' in results
        assert 'total_count' in results
        assert isinstance(results['items'], list)
        assert isinstance(results['updates'], list)
        assert isinstance(results['total_count'], int)

    def test_search_respects_limit(self, db, project_id):
        for i in range(5):
            db.create_item(
                project_id, 'issue',
                f'Limit Test Item {i}', '', 3)
        results = db.search(
            project_id, 'Limit Test', limit=2)
        assert len(results['items']) <= 2


# ===================================================================
# Relationships
# ===================================================================

class TestRelationships:
    def test_add_relationship(self, db, project_id):
        id1 = db.create_item(
            project_id, 'issue', 'Blocker', '', 3)
        id2 = db.create_item(
            project_id, 'issue', 'Blocked', '', 3)
        result = db.add_relationship(id1, id2, 'blocks')
        assert result['success'] is True

    def test_duplicate_relationship_returns_error(
            self, db, project_id):
        id1 = db.create_item(
            project_id, 'issue', 'R1', '', 3)
        id2 = db.create_item(
            project_id, 'issue', 'R2', '', 3)
        db.add_relationship(id1, id2, 'blocks')
        result = db.add_relationship(id1, id2, 'blocks')
        assert result['success'] is False
        assert 'error' in result

    def test_get_item_relationships(self, db, project_id):
        id1 = db.create_item(
            project_id, 'issue', 'Src', '', 3)
        id2 = db.create_item(
            project_id, 'issue', 'Tgt', '', 3)
        db.add_relationship(id1, id2, 'relates_to')
        rels = db.get_item_relationships(id1)
        assert len(rels) >= 1

    def test_delete_relationship(self, db, project_id):
        id1 = db.create_item(
            project_id, 'issue', 'S', '', 3)
        id2 = db.create_item(
            project_id, 'issue', 'T', '', 3)
        db.add_relationship(id1, id2, 'blocks')
        result = db.remove_relationship(id1, id2, 'blocks')
        assert result['success'] is True


# ===================================================================
# Tags
# ===================================================================

class TestTags:
    def test_create_tag(self, db, project_id):
        tag_id = db.ensure_tag(project_id, 'important')
        assert tag_id > 0

    def test_duplicate_tag_returns_same_id(self, db, project_id):
        id1 = db.ensure_tag(project_id, 'mytag')
        id2 = db.ensure_tag(project_id, 'mytag')
        assert id1 == id2

    def test_add_tag_to_item(self, db, project_id):
        item_id = db.create_item(
            project_id, 'issue', 'Tagged Item', '', 3)
        result = db.add_tag_to_item(item_id, 'bug')
        assert result['success'] is True

    def test_duplicate_tag_assignment_returns_error(
            self, db, project_id):
        item_id = db.create_item(
            project_id, 'issue', 'Double Tag', '', 3)
        db.add_tag_to_item(item_id, 'dup')
        result = db.add_tag_to_item(item_id, 'dup')
        assert result['success'] is False

    def test_list_tags(self, db, project_id):
        db.ensure_tag(project_id, 'tag_a')
        db.ensure_tag(project_id, 'tag_b')
        tags = db.get_project_tags(project_id)
        names = [t['name'] for t in tags]
        assert 'tag_a' in names
        assert 'tag_b' in names


# ===================================================================
# File links, decisions, status history
# ===================================================================

class TestFileLinksAndDecisions:
    def test_link_file_to_item(self, db, project_id):
        item_id = db.create_item(
            project_id, 'issue', 'File Link', '', 3)
        result = db.link_file(item_id, '/src/main.py')
        assert result['success'] is True

    def test_add_decision(self, db, project_id):
        item_id = db.create_item(
            project_id, 'feature', 'Decision Item', '', 3)
        result = db.add_decision(
            item_id, 'Use SQLite',
            'PostgreSQL, MySQL', 'Zero config')
        assert result['success'] is True

    def test_status_history_recorded_on_advance(
            self, db, project_id):
        item_id = db.create_item(
            project_id, 'issue', 'History Test', '', 3)
        db.advance_status(item_id)
        history = db.get_status_history(item_id)
        assert len(history) >= 1


# ===================================================================
# Parent-child
# ===================================================================

class TestParentChild:
    def test_set_parent(self, db, project_id):
        epic_id = db.create_item(
            project_id, 'epic', 'My Epic', '', 3)
        child_id = db.create_item(
            project_id, 'issue', 'Child Issue', '', 3)
        result = db.set_parent(child_id, epic_id)
        assert result['success'] is True

    def test_epic_progress(self, db, project_id):
        epic_id = db.create_item(
            project_id, 'epic', 'Progress Epic', '', 3)
        c1 = db.create_item(
            project_id, 'issue', 'Child 1', '', 3)
        c2 = db.create_item(
            project_id, 'issue', 'Child 2', '', 3)
        db.set_parent(c1, epic_id)
        db.set_parent(c2, epic_id)
        db.close_item(c1)
        progress = db.get_epic_progress(epic_id)
        assert progress['total'] == 2
        assert progress['completed'] == 1

    def test_list_children(self, db, project_id):
        epic_id = db.create_item(
            project_id, 'epic', 'Parent', '', 3)
        c1 = db.create_item(
            project_id, 'issue', 'Kid 1', '', 3)
        c2 = db.create_item(
            project_id, 'issue', 'Kid 2', '', 3)
        db.set_parent(c1, epic_id)
        db.set_parent(c2, epic_id)
        children = db.get_children(epic_id)
        assert len(children) == 2
