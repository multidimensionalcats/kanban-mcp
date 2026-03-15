-- Migration: Add FULLTEXT indexes for search functionality
-- Run with: mysql -u $KANBAN_DB_USER -p $KANBAN_DB_NAME < migrations/002_add_fulltext_search.sql

-- Add FULLTEXT index on items (title + description)
-- Note: MySQL requires InnoDB tables for FULLTEXT in 5.6+, MyISAM for earlier
ALTER TABLE items ADD FULLTEXT INDEX idx_items_fulltext (title, description);

-- Add FULLTEXT index on updates (content)
ALTER TABLE updates ADD FULLTEXT INDEX idx_updates_fulltext (content);
