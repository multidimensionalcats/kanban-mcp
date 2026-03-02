-- Migration: Add embeddings table for vector semantic search
-- Run with: mysql -u $KANBAN_DB_USER -p $KANBAN_DB_NAME < migrations/003_add_embeddings.sql

-- Create embeddings table for storing vector embeddings
CREATE TABLE IF NOT EXISTS embeddings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    source_type ENUM('item', 'decision', 'update') NOT NULL,
    source_id INT NOT NULL,
    content_hash CHAR(32) NOT NULL,           -- MD5 of embedded text
    model VARCHAR(50) NOT NULL DEFAULT 'nomic-embed-text-v1.5',
    vector BLOB NOT NULL,                      -- packed float32 (768 * 4 = 3072 bytes)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_source_model (source_type, source_id, model),
    INDEX idx_source (source_type, source_id),
    INDEX idx_model (model)
);
