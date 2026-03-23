-- 013_manager_routing.sql
-- Three-way routing: client ↔ manager ↔ AI
-- When manager is active, client messages go to manager (not AI)

ALTER TABLE conversations ADD COLUMN IF NOT EXISTS manager_is_active BOOLEAN DEFAULT FALSE;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS last_manager_activity_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_conversations_manager_active
  ON conversations (manager_is_active) WHERE manager_is_active = TRUE;
