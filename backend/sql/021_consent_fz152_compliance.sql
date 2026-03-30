-- ============================================================================
-- 021: Consent flow — ФЗ-152 compliance (Phase 8)
-- 1) Add automated_decisions purpose (Art. 16 ФЗ-152)
-- 2) Make crm_sync required (core function, not optional)
-- 3) Add is_minor column for Art. 9 Part 6 compliance
-- ============================================================================

-- 1. New required purpose: automated AI decisions (Art. 16 ФЗ-152)
INSERT INTO agent_consent_purposes (id, title_ru, description, required, version) VALUES
  ('automated_decisions',
   'Автоматизированные решения ИИ',
   'Согласие на принятие решений на основе автоматизированной обработки данных ИИ-ассистентом (ст. 16 ФЗ-152). Вы имеете право на информацию о логике принятия решений и на обжалование.',
   TRUE, '1.0')
ON CONFLICT (id) DO NOTHING;

-- 2. crm_sync → required + updated title
UPDATE agent_consent_purposes
SET required = TRUE,
    title_ru = 'Передача данных специалистам'
WHERE id = 'crm_sync';

-- 3. Track minor status in consent records and audit log (Art. 9 Part 6)
ALTER TABLE agent_consent_records
  ADD COLUMN IF NOT EXISTS is_minor BOOLEAN DEFAULT NULL;

ALTER TABLE agent_consent_audit_log
  ADD COLUMN IF NOT EXISTS is_minor BOOLEAN DEFAULT NULL;
