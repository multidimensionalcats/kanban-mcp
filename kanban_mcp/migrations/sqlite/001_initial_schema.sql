-- Migration: Initial schema for kanban-mcp (SQLite)
-- Translated from MySQL 001_initial_schema.sql + 003_add_embeddings.sql

-- ============================================================
-- Schema migration tracking
-- ============================================================

CREATE TABLE IF NOT EXISTS schema_migrations (
    filename TEXT PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT (datetime('now'))
);

-- ============================================================
-- Lookup tables
-- ============================================================

CREATE TABLE IF NOT EXISTS item_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS statuses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS type_status_workflow (
    type_id INTEGER NOT NULL,
    status_id INTEGER NOT NULL,
    sequence INTEGER NOT NULL,
    PRIMARY KEY (type_id, status_id),
    FOREIGN KEY (type_id) REFERENCES item_types(id),
    FOREIGN KEY (status_id) REFERENCES statuses(id)
);

-- ============================================================
-- Core tables
-- ============================================================

CREATE TABLE IF NOT EXISTS projects (
    id TEXT NOT NULL PRIMARY KEY,
    directory_path TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    type_id INTEGER NOT NULL,
    status_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    priority INTEGER DEFAULT 3,
    created_at TIMESTAMP DEFAULT (datetime('now')),
    updated_at TIMESTAMP DEFAULT (datetime('now')),
    closed_at TIMESTAMP DEFAULT NULL,
    complexity INTEGER DEFAULT NULL,
    parent_id INTEGER DEFAULT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (type_id) REFERENCES item_types(id),
    FOREIGN KEY (status_id) REFERENCES statuses(id),
    FOREIGN KEY (parent_id) REFERENCES items(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_project_status ON items(project_id, status_id);
CREATE INDEX IF NOT EXISTS idx_type_status ON items(type_id, status_id);
CREATE INDEX IF NOT EXISTS idx_items_parent_id ON items(parent_id);

CREATE TABLE IF NOT EXISTS updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT (datetime('now')),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_project_created ON updates(project_id, created_at);

CREATE TABLE IF NOT EXISTS update_items (
    update_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    PRIMARY KEY (update_id, item_id),
    FOREIGN KEY (update_id) REFERENCES updates(id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS item_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_item_id INTEGER NOT NULL,
    target_item_id INTEGER NOT NULL,
    relationship_type TEXT NOT NULL CHECK(relationship_type IN ('blocks', 'depends_on', 'relates_to', 'duplicates')),
    created_at TIMESTAMP DEFAULT (datetime('now')),
    UNIQUE (source_item_id, target_item_id, relationship_type),
    FOREIGN KEY (source_item_id) REFERENCES items(id) ON DELETE CASCADE,
    FOREIGN KEY (target_item_id) REFERENCES items(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    color TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT (datetime('now')),
    UNIQUE (project_id, name),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_project_tags ON tags(project_id);

CREATE TABLE IF NOT EXISTS item_tags (
    item_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT (datetime('now')),
    PRIMARY KEY (item_id, tag_id),
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tag_items ON item_tags(tag_id);

CREATE TABLE IF NOT EXISTS item_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    line_start INTEGER DEFAULT NULL,
    line_end INTEGER DEFAULT NULL,
    created_at TIMESTAMP DEFAULT (datetime('now')),
    UNIQUE (item_id, file_path, line_start, line_end),
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS item_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    choice TEXT NOT NULL,
    rejected_alternatives TEXT DEFAULT NULL,
    rationale TEXT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT (datetime('now')),
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_item_decisions_item ON item_decisions(item_id);

CREATE TABLE IF NOT EXISTS status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    old_status_id INTEGER DEFAULT NULL,
    new_status_id INTEGER NOT NULL,
    change_type TEXT NOT NULL CHECK(change_type IN ('create', 'advance', 'revert', 'set', 'close', 'auto_advance')),
    changed_at TIMESTAMP DEFAULT (datetime('now')),
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE,
    FOREIGN KEY (old_status_id) REFERENCES statuses(id),
    FOREIGN KEY (new_status_id) REFERENCES statuses(id)
);

CREATE INDEX IF NOT EXISTS idx_item_changed ON status_history(item_id, changed_at);

-- ============================================================
-- Embeddings table (for vector semantic search)
-- ============================================================

CREATE TABLE IF NOT EXISTS embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL CHECK(source_type IN ('item', 'decision', 'update')),
    source_id INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT 'nomic-embed-text-v1.5',
    vector BLOB NOT NULL,
    created_at TIMESTAMP DEFAULT (datetime('now')),
    UNIQUE (source_type, source_id, model)
);

CREATE INDEX IF NOT EXISTS idx_source ON embeddings(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_model ON embeddings(model);

-- ============================================================
-- Trigger for updated_at
-- ============================================================

CREATE TRIGGER IF NOT EXISTS items_updated_at AFTER UPDATE ON items
FOR EACH ROW
BEGIN
    UPDATE items SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- ============================================================
-- Seed data
-- ============================================================

INSERT OR IGNORE INTO item_types (id, name) VALUES
    (1, 'issue'),
    (2, 'todo'),
    (3, 'feature'),
    (4, 'diary'),
    (5, 'epic'),
    (6, 'question');

INSERT OR IGNORE INTO statuses (id, name) VALUES
    (1, 'backlog'),
    (2, 'todo'),
    (3, 'in_progress'),
    (4, 'review'),
    (5, 'done'),
    (6, 'closed');

-- Workflow: which statuses are valid for each type, and in what order
INSERT OR IGNORE INTO type_status_workflow (type_id, status_id, sequence) VALUES
    -- issue: backlog -> todo -> in_progress -> review -> done -> closed
    (1, 1, 1), (1, 2, 2), (1, 3, 3), (1, 4, 4), (1, 5, 5), (1, 6, 6),
    -- todo: backlog -> todo -> in_progress -> done
    (2, 1, 1), (2, 2, 2), (2, 3, 3), (2, 5, 4),
    -- feature: backlog -> todo -> in_progress -> review -> done -> closed
    (3, 1, 1), (3, 2, 2), (3, 3, 3), (3, 4, 4), (3, 5, 5), (3, 6, 6),
    -- diary: done (single state)
    (4, 5, 1),
    -- epic: backlog -> todo -> in_progress -> review -> done -> closed
    (5, 1, 1), (5, 2, 2), (5, 3, 3), (5, 4, 4), (5, 5, 5), (5, 6, 6),
    -- question: backlog -> review -> closed
    (6, 1, 1), (6, 4, 2), (6, 6, 3);
