-- Migration: MariaDB compatibility
-- Converts collation from MySQL 8.0-only utf8mb4_0900_ai_ci to the
-- universally supported utf8mb4_unicode_ci.  Safe to run on MySQL or
-- MariaDB; converting a table already on utf8mb4_unicode_ci is a no-op.
--
-- FK checks must be disabled during charset conversion because converting
-- a parent table makes its collation temporarily differ from child tables
-- that haven't been converted yet, causing MySQL to reject the FK.

SET FOREIGN_KEY_CHECKS = 0;

-- Fix type mismatch: tags.project_id was VARCHAR(16) but projects.id is
-- CHAR(16).  Must match for FK validity.  MariaDB requires an explicit
-- DROP/ADD even with FOREIGN_KEY_CHECKS=0 for MODIFY COLUMN.
ALTER TABLE tags DROP FOREIGN KEY tags_ibfk_1;
ALTER TABLE tags MODIFY project_id CHAR(16) NOT NULL;
ALTER TABLE tags ADD CONSTRAINT tags_ibfk_1
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;

ALTER TABLE item_types        CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE statuses          CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE type_status_workflow CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE projects          CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE items             CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE updates           CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE update_items      CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE item_relationships CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE tags              CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE item_tags         CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE item_files        CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE item_decisions    CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE status_history    CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE embeddings        CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE schema_migrations CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Rebuild fulltext indexes that CONVERT TO CHARACTER SET invalidates on InnoDB.
-- OPTIMIZE TABLE performs a recreate+analyze which rebuilds the FTS index.
OPTIMIZE TABLE items;
OPTIMIZE TABLE updates;

SET FOREIGN_KEY_CHECKS = 1;
