-- 015: Add lead_id to chat mapping for reliable note delivery
-- forward_agent_response needs lead_id to add AI response notes

ALTER TABLE agent_chat_mapping ADD COLUMN IF NOT EXISTS amocrm_lead_id INTEGER;
