-- Migration 024: Fix missing ON DELETE for agent_manager_messages FK
-- Bug: agent_conversation_id references conversations(id) without ON DELETE,
-- causing orphaned rows when conversations are deleted.

ALTER TABLE agent_manager_messages
  DROP CONSTRAINT IF EXISTS agent_manager_messages_agent_conversation_id_fkey;

ALTER TABLE agent_manager_messages
  ADD CONSTRAINT agent_manager_messages_agent_conversation_id_fkey
  FOREIGN KEY (agent_conversation_id) REFERENCES conversations(id) ON DELETE SET NULL;
