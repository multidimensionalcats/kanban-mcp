-- Migration: Add ON DELETE CASCADE to project FK constraints
-- Run with: mysql -u $KANBAN_DB_USER -p $KANBAN_DB_NAME < migrations/004_add_cascades_and_indexes.sql
--
-- items.project_id and updates.project_id lack CASCADE, so deleting a project
-- leaves orphaned rows. This migration fixes that.
--
-- Note: item_relationships, update_items, tags, status_history, item_tags,
-- item_decisions, and item_files already have ON DELETE CASCADE.
-- Indexes on item_relationships(target_item_id) and update_items(item_id)
-- already exist.

-- items.project_id → projects(id) with CASCADE
ALTER TABLE items DROP FOREIGN KEY items_ibfk_1;
ALTER TABLE items ADD CONSTRAINT items_project_fk
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;

-- updates.project_id → projects(id) with CASCADE
ALTER TABLE updates DROP FOREIGN KEY updates_ibfk_1;
ALTER TABLE updates ADD CONSTRAINT updates_project_fk
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;
