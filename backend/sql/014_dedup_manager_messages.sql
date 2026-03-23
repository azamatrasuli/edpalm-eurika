-- 014: Deduplicate manager messages by amocrm_msgid
-- Prevents duplicate webhook deliveries from creating duplicate messages.

CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_manager_messages_msgid_unique
  ON agent_manager_messages(amocrm_msgid)
  WHERE amocrm_msgid IS NOT NULL;
