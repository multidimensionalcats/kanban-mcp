#!/usr/bin/env python3
"""
Hostile edge case tests — designed to break things.

Parametrized across all available backends via the `db` fixture.
"""

import pytest


# ===================================================================
# Category 1: Duplicate/Constraint Handling
# ===================================================================

class TestDuplicateConstraints:
    def test_duplicate_relationship_graceful(self, db, project_id):
        id1 = db.create_item(
            project_id, 'issue', 'A', '', 3)
        id2 = db.create_item(
            project_id, 'issue', 'B', '', 3)
        db.add_relationship(id1, id2, 'blocks')
        result = db.add_relationship(id1, id2, 'blocks')
        assert result['success'] is False
        assert 'error' in result

    def test_duplicate_tag_name_graceful(self, db, project_id):
        """Create tag "foo" twice — second should return same id."""
        id1 = db.ensure_tag(project_id, 'foo')
        id2 = db.ensure_tag(project_id, 'foo')
        assert id1 == id2

    def test_duplicate_tag_assignment_graceful(
            self, db, project_id):
        item_id = db.create_item(
            project_id, 'issue', 'Dup Tag', '', 3)
        db.add_tag_to_item(item_id, 'dup')
        result = db.add_tag_to_item(item_id, 'dup')
        assert result['success'] is False

    def test_rename_tag_to_existing_name(self, db, project_id):
        db.ensure_tag(project_id, 'alpha')
        tag_id = db.ensure_tag(project_id, 'beta')
        result = db.update_tag(tag_id, name='alpha')
        assert result['success'] is False

    def test_duplicate_project_insert_ignore(self, db):
        pid1 = db.ensure_project('/tmp/dup-proj', 'Dup')
        pid2 = db.ensure_project('/tmp/dup-proj', 'Dup')
        assert pid1 == pid2


# ===================================================================
# Category 2: CASCADE Integrity
# ===================================================================

class TestCascadeIntegrity:
    def test_delete_item_cascades_relationships(
            self, db, project_id):
        id1 = db.create_item(
            project_id, 'issue', 'Src', '', 3)
        id2 = db.create_item(
            project_id, 'issue', 'Tgt', '', 3)
        db.add_relationship(id1, id2, 'blocks')
        db.delete_item(id1)
        rels = db.get_item_relationships(id2)
        # rels is a dict with 'outgoing' and 'incoming'
        all_rels = rels.get('outgoing', []) + rels.get(
            'incoming', [])
        assert len(all_rels) == 0

    def test_delete_item_cascades_tags(self, db, project_id):
        item_id = db.create_item(
            project_id, 'issue', 'Tagged', '', 3)
        db.add_tag_to_item(item_id, 'to_cascade')
        db.delete_item(item_id)
        tags = db.get_item_tags(item_id)
        assert len(tags) == 0

    def test_delete_item_cascades_files(self, db, project_id):
        item_id = db.create_item(
            project_id, 'issue', 'Filed', '', 3)
        db.link_file(item_id, '/src/main.py')
        db.delete_item(item_id)
        files = db.get_item_files(item_id)
        assert len(files) == 0

    def test_delete_item_cascades_decisions(self, db, project_id):
        item_id = db.create_item(
            project_id, 'feature', 'Decided', '', 3)
        db.add_decision(item_id, 'Use X', 'Y, Z', 'Because')
        db.delete_item(item_id)
        decisions = db.get_item_decisions(item_id)
        assert len(decisions) == 0

    def test_delete_item_cascades_status_history(
            self, db, project_id):
        item_id = db.create_item(
            project_id, 'issue', 'History', '', 3)
        db.advance_status(item_id)
        db.delete_item(item_id)
        history = db.get_status_history(item_id)
        assert len(history) == 0

    def test_delete_parent_cascades_children(
            self, db, project_id):
        epic = db.create_item(
            project_id, 'epic', 'Epic', '', 3)
        child = db.create_item(
            project_id, 'issue', 'Child', '', 3)
        db.set_parent(child, epic)
        db.delete_item(epic)
        assert db.get_item(child) is None

    def test_foreign_keys_actually_enforced(self, db):
        """Insert item with nonexistent project_id — expect error."""
        with pytest.raises(Exception):
            with db._db_cursor(commit=True) as cursor:
                cursor.execute(
                    db._sql(
                        "INSERT INTO items"
                        " (project_id, type_id, status_id, title)"
                        " VALUES (%s, %s, %s, %s)"),
                    ('nonexistent_id!!', 1, 1, 'Bad'))


# ===================================================================
# Category 3: Timestamp Behavior
# ===================================================================

class TestTimestamps:
    def test_created_at_auto_populated(self, db, project_id):
        item_id = db.create_item(
            project_id, 'issue', 'Timestamp', '', 3)
        item = db.get_item(item_id)
        assert item['created_at'] is not None

    def test_closed_at_null_before_close(self, db, project_id):
        item_id = db.create_item(
            project_id, 'issue', 'Not Closed', '', 3)
        item = db.get_item(item_id)
        assert item['closed_at'] is None

    def test_closed_at_set_on_close(self, db, project_id):
        item_id = db.create_item(
            project_id, 'issue', 'Will Close', '', 3)
        db.close_item(item_id)
        item = db.get_item(item_id)
        assert item['closed_at'] is not None

    def test_timestamps_are_parseable(self, db, project_id):
        from datetime import datetime
        item_id = db.create_item(
            project_id, 'issue', 'Parse', '', 3)
        item = db.get_item(item_id)
        ts = item['created_at']
        if isinstance(ts, str):
            datetime.fromisoformat(ts)
        else:
            assert hasattr(ts, 'year')


# ===================================================================
# Category 4: Type Coercion and Boundaries
# ===================================================================

class TestBoundaries:
    def test_priority_boundary_values(self, db, project_id):
        for p in [1, 5]:
            item_id = db.create_item(
                project_id, 'issue', f'P{p}', '', p)
            item = db.get_item(item_id)
            assert item['priority'] == p

    def test_complexity_null_allowed(self, db, project_id):
        item_id = db.create_item(
            project_id, 'issue', 'No Complexity', '', 3)
        item = db.get_item(item_id)
        assert item['complexity'] is None

    def test_empty_string_title(self, db, project_id):
        # Empty title should still work (no NOT NULL constraint
        # on empty string)
        item_id = db.create_item(
            project_id, 'issue', '', '', 3)
        item = db.get_item(item_id)
        assert item['title'] == ''

    def test_very_long_title(self, db, project_id):
        long_title = 'A' * 10000
        item_id = db.create_item(
            project_id, 'issue', long_title, '', 3)
        item = db.get_item(item_id)
        assert len(item['title']) == 10000

    def test_very_long_description(self, db, project_id):
        long_desc = 'B' * 100000
        item_id = db.create_item(
            project_id, 'issue', 'Long Desc', long_desc, 3)
        item = db.get_item(item_id)
        assert len(item['description']) == 100000

    def test_item_id_type_consistency(self, db, project_id):
        item_id = db.create_item(
            project_id, 'issue', 'Type Check', '', 3)
        assert isinstance(item_id, int)
        item = db.get_item(item_id)
        assert isinstance(item['id'], int)


# ===================================================================
# Category 5: Unicode and Special Characters
# ===================================================================

class TestUnicodeAndSpecialChars:
    def test_unicode_title(self, db, project_id):
        item_id = db.create_item(
            project_id, 'issue', '修复数据库连接 🔧', '', 3)
        item = db.get_item(item_id)
        assert '修复' in item['title']
        assert '🔧' in item['title']

    def test_unicode_description(self, db, project_id):
        desc = '🎉🔥💯' * 100
        item_id = db.create_item(
            project_id, 'issue', 'Emoji', desc, 3)
        item = db.get_item(item_id)
        assert '🎉' in item['description']

    def test_unicode_tag_name(self, db, project_id):
        tag_id = db.ensure_tag(project_id, 'バグ')
        assert tag_id > 0
        item_id = db.create_item(
            project_id, 'issue', 'Japanese', '', 3)
        result = db.add_tag_to_item(item_id, 'バグ')
        assert result['success'] is True

    def test_unicode_search(self, db, project_id):
        db.create_item(
            project_id, 'issue', '数据库修复', '', 3)
        results = db.search(project_id, '数据库', limit=10)
        assert results['total_count'] >= 1

    def test_sql_injection_in_search(self, db, project_id):
        results = db.search(
            project_id,
            "'; DROP TABLE items; --",
            limit=10)
        assert isinstance(results, dict)
        # Verify table still exists
        item_id = db.create_item(
            project_id, 'issue', 'Still Here', '', 3)
        assert item_id > 0

    def test_percent_in_search(self, db, project_id):
        db.create_item(
            project_id, 'issue', '100% complete', '', 3)
        results = db.search(project_id, '100%', limit=10)
        # Should not crash
        assert isinstance(results, dict)

    def test_underscore_in_search(self, db, project_id):
        db.create_item(
            project_id, 'issue', 'my_var_name', '', 3)
        results = db.search(
            project_id, 'my_var', limit=10)
        assert isinstance(results, dict)

    def test_single_quote_in_title(self, db, project_id):
        item_id = db.create_item(
            project_id, 'issue', "It's broken", '', 3)
        item = db.get_item(item_id)
        assert item['title'] == "It's broken"

    def test_backslash_in_title(self, db, project_id):
        item_id = db.create_item(
            project_id, 'issue', r'path\to\file', '', 3)
        item = db.get_item(item_id)
        assert 'path' in item['title']

    def test_null_bytes_in_content(self, db, project_id):
        content = 'before\x00after'
        update_id = db.add_update(project_id, content, [])
        assert update_id > 0


# ===================================================================
# Category 6: Concurrent Access (SQLite file-based only)
# ===================================================================

class TestConcurrentAccess:
    def test_concurrent_reads(self, backend, tmp_path):
        """Two KanbanDB instances reading same file simultaneously."""
        if backend.backend_type != 'sqlite':
            pytest.skip("SQLite-specific test")
        from kanban_mcp.db.sqlite_backend import SQLiteBackend
        from kanban_mcp.setup import auto_migrate
        from kanban_mcp.core import KanbanDB

        db_path = str(tmp_path / "concurrent.db")
        b1 = SQLiteBackend(db_path=db_path)
        auto_migrate(b1)
        b2 = SQLiteBackend(db_path=db_path)

        db1 = KanbanDB(backend=b1)
        db2 = KanbanDB(backend=b2)

        pid = db1.ensure_project('/tmp/concurrent', 'Conc')
        db1.create_item(pid, 'issue', 'Shared', '', 3)

        # Both should be able to read
        items1 = db1.list_items(pid)
        items2 = db2.list_items(pid)
        assert len(items1) >= 1
        assert len(items2) >= 1

    def test_concurrent_write_then_read(self, backend, tmp_path):
        if backend.backend_type != 'sqlite':
            pytest.skip("SQLite-specific test")
        from kanban_mcp.db.sqlite_backend import SQLiteBackend
        from kanban_mcp.setup import auto_migrate
        from kanban_mcp.core import KanbanDB

        db_path = str(tmp_path / "wr.db")
        b1 = SQLiteBackend(db_path=db_path)
        auto_migrate(b1)
        b2 = SQLiteBackend(db_path=db_path)

        db1 = KanbanDB(backend=b1)
        db2 = KanbanDB(backend=b2)

        pid = db1.ensure_project('/tmp/wr', 'WR')
        db1.create_item(pid, 'issue', 'Written', '', 3)

        # Reader should see the write
        items = db2.list_items(pid)
        assert any(i['title'] == 'Written' for i in items)

    def test_busy_timeout_prevents_immediate_failure(
            self, backend, tmp_path):
        if backend.backend_type != 'sqlite':
            pytest.skip("SQLite-specific test")
        from kanban_mcp.db.sqlite_backend import SQLiteBackend
        from kanban_mcp.setup import auto_migrate

        db_path = str(tmp_path / "busy.db")
        b = SQLiteBackend(db_path=db_path)
        auto_migrate(b)
        # Just verify busy_timeout is set
        with b.db_cursor() as cursor:
            cursor.execute('PRAGMA busy_timeout')
            timeout = cursor.fetchone()[0]
        assert timeout == 5000


# ===================================================================
# Category 7: Search Edge Cases
# ===================================================================

class TestSearchEdgeCases:
    def test_search_empty_query(self, db, project_id):
        results = db.search(project_id, '', limit=10)
        assert isinstance(results, dict)

    def test_search_whitespace_query(self, db, project_id):
        results = db.search(project_id, '   ', limit=10)
        assert isinstance(results, dict)

    def test_search_no_results(self, db, project_id):
        results = db.search(
            project_id, 'xyznonexistent', limit=10)
        assert results['total_count'] == 0

    def test_search_special_sql_chars(self, db, project_id):
        for char in ['%', '_', "'", '\\']:
            results = db.search(
                project_id, char, limit=10)
            assert isinstance(results, dict)

    def test_search_very_long_query(self, db, project_id):
        long_query = 'a' * 1000
        results = db.search(
            project_id, long_query, limit=10)
        assert isinstance(results, dict)

    def test_search_html_in_content(self, db, project_id):
        db.create_item(
            project_id, 'issue', 'XSS Test',
            '<script>alert(1)</script>', 3)
        results = db.search(
            project_id, 'alert', limit=10)
        assert results['total_count'] >= 1


# ===================================================================
# Category 8: Migration Integrity
# ===================================================================

class TestMigrationIntegrity:
    def test_migration_creates_all_tables(self, backend):
        expected = {
            'schema_migrations', 'item_types', 'statuses',
            'type_status_workflow', 'projects', 'items',
            'updates', 'update_items', 'item_relationships',
            'tags', 'item_tags', 'item_files', 'item_decisions',
            'status_history', 'embeddings',
        }
        with backend.db_cursor() as cursor:
            if backend.backend_type == 'sqlite':
                cursor.execute(
                    "SELECT name FROM sqlite_master"
                    " WHERE type='table'"
                    " AND name NOT LIKE 'sqlite_%'")
            else:
                cursor.execute(
                    "SELECT TABLE_NAME"
                    " FROM information_schema.TABLES"
                    " WHERE TABLE_SCHEMA = DATABASE()")
            tables = {row[0] for row in cursor.fetchall()}
        assert expected.issubset(tables), (
            f"Missing tables: {expected - tables}")

    def test_migration_idempotent(self, backend):
        from kanban_mcp.setup import auto_migrate
        # Run migrations again — should not error
        auto_migrate(backend)

    def test_migration_seeds_item_types(self, backend):
        with backend.db_cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM item_types")
            types = cursor.fetchall()
        assert len(types) == 6
        names = {t['name'] for t in types}
        assert 'issue' in names
        assert 'epic' in names

    def test_migration_seeds_statuses(self, backend):
        with backend.db_cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM statuses")
            statuses = cursor.fetchall()
        assert len(statuses) == 6
        names = {s['name'] for s in statuses}
        assert 'backlog' in names
        assert 'closed' in names

    def test_migration_seeds_workflows(self, backend):
        with backend.db_cursor(dictionary=True) as cursor:
            cursor.execute(
                "SELECT * FROM type_status_workflow")
            workflows = cursor.fetchall()
        assert len(workflows) > 0

    def test_schema_migrations_tracked(self, backend):
        with backend.db_cursor(dictionary=True) as cursor:
            cursor.execute(
                "SELECT * FROM schema_migrations")
            records = cursor.fetchall()
        assert len(records) >= 1
        filenames = [r['filename'] for r in records]
        assert any(
            '001_initial_schema' in f for f in filenames)

    def test_updated_at_trigger_exists_sqlite(self, backend):
        if backend.backend_type != 'sqlite':
            pytest.skip("SQLite-specific test")
        with backend.db_cursor() as cursor:
            cursor.execute(
                "SELECT name FROM sqlite_master"
                " WHERE type='trigger'"
                " AND name='items_updated_at'")
            row = cursor.fetchone()
        assert row is not None


# ===================================================================
# Category 9: Error Recovery
# ===================================================================

class TestErrorRecovery:
    def test_failed_transaction_rolls_back(self, db, project_id):
        """Error mid-operation should not leave partial state."""
        item_id = db.create_item(
            project_id, 'issue', 'Rollback Test', '', 3)
        try:
            with db._db_cursor(commit=True) as cursor:
                cursor.execute(
                    db._sql(
                        "UPDATE items SET title = %s"
                        " WHERE id = %s"),
                    ('Modified', item_id))
                # Force an error
                raise RuntimeError("Simulated error")
        except RuntimeError:
            pass
        item = db.get_item(item_id)
        assert item['title'] == 'Rollback Test'

    def test_advance_past_final_status(self, db, project_id):
        """Try to advance past the final status."""
        item_id = db.create_item(
            project_id, 'diary', 'Entry', 'Content', 3)
        # Diary starts at 'done' — can't advance
        result = db.advance_status(item_id)
        assert result['success'] is False

    def test_circular_parent_reference(self, db, project_id):
        """Set item as its own parent."""
        item_id = db.create_item(
            project_id, 'issue', 'Self Ref', '', 3)
        result = db.set_parent(item_id, item_id)
        # Should either fail or handle gracefully
        # The behavior depends on implementation
        assert isinstance(result, dict)

    def test_deep_parent_chain(self, db, project_id):
        """10-level deep parent hierarchy."""
        parent = db.create_item(
            project_id, 'epic', 'Root', '', 3)
        for i in range(10):
            child = db.create_item(
                project_id, 'issue', f'Level {i}', '', 3)
            db.set_parent(child, parent)
            parent = child
        # The deepest child should still be retrievable
        item = db.get_item(parent)
        assert item is not None
