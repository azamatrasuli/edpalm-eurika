-- 026: Grade filtering and enriched metadata for teacher knowledge base
-- Adds grade range, subject, and book_title columns to knowledge_chunks.
-- Nullable columns — sales/support chunks are not affected.

ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS grade SMALLINT;
ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS grade_to SMALLINT;
ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS subject TEXT;
ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS book_title TEXT;

-- Composite index for teacher searches with grade filtering
CREATE INDEX IF NOT EXISTS idx_chunks_teacher_lookup
    ON knowledge_chunks (namespace, grade, grade_to)
    WHERE namespace = 'teacher';
