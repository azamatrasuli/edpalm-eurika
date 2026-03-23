-- 012_pipeline_alignment.sql
-- Выравнивание схемы под бизнес-процессы ЦПСО: типология клиентов, стадии воронки, гейт менеджера

-- 1. Расширить client_type в agent_user_profiles
-- Добавляем 'renewal', 'reanimation', 'unknown' к существующим 'existing', 'new'
ALTER TABLE agent_user_profiles DROP CONSTRAINT IF EXISTS agent_user_profiles_client_type_check;
ALTER TABLE agent_user_profiles ADD CONSTRAINT agent_user_profiles_client_type_check
  CHECK (client_type IN ('existing', 'new', 'renewal', 'reanimation', 'unknown'));

-- 2. Добавить воронку и стадию к conversations
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS funnel_stage TEXT;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS funnel_pipeline TEXT;

CREATE INDEX IF NOT EXISTS idx_conversations_funnel_stage
  ON conversations (funnel_stage) WHERE funnel_stage IS NOT NULL;

-- 3. Расширить agent_deal_mapping: гейт менеджера, причины отказа, история стадий
ALTER TABLE agent_deal_mapping ADD COLUMN IF NOT EXISTS manager_approved_at TIMESTAMPTZ;
ALTER TABLE agent_deal_mapping ADD COLUMN IF NOT EXISTS decline_reasons JSONB;
ALTER TABLE agent_deal_mapping ADD COLUMN IF NOT EXISTS stage_history JSONB DEFAULT '[]';
ALTER TABLE agent_deal_mapping ADD COLUMN IF NOT EXISTS funnel_stage TEXT;
