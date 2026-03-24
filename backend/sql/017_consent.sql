-- ============================================================================
-- 017: Consent management (ФЗ-152 compliance)
-- Three tables: purposes (reference), records (current state), audit_log (append-only)
-- ============================================================================

-- 1. Consent purposes — what the user can agree/disagree to
CREATE TABLE IF NOT EXISTS agent_consent_purposes (
  id          TEXT PRIMARY KEY,
  title_ru    TEXT NOT NULL,
  description TEXT NOT NULL,
  required    BOOLEAN NOT NULL DEFAULT FALSE,
  version     TEXT NOT NULL DEFAULT '1.0',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Current consent state per user per purpose (one active record)
CREATE TABLE IF NOT EXISTS agent_consent_records (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_id    TEXT NOT NULL,
  purpose_id  TEXT NOT NULL REFERENCES agent_consent_purposes(id),
  granted     BOOLEAN NOT NULL,
  version     TEXT NOT NULL DEFAULT '1.0',
  granted_at  TIMESTAMPTZ,
  revoked_at  TIMESTAMPTZ,
  method      TEXT NOT NULL DEFAULT 'settings',
  ip_address  TEXT,
  user_agent  TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(actor_id, purpose_id)
);

CREATE INDEX IF NOT EXISTS idx_consent_records_actor
  ON agent_consent_records(actor_id);

-- 3. Append-only audit trail (never updated or deleted)
CREATE TABLE IF NOT EXISTS agent_consent_audit_log (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_id    TEXT NOT NULL,
  purpose_id  TEXT NOT NULL,
  action      TEXT NOT NULL CHECK (action IN ('grant', 'revoke')),
  version     TEXT NOT NULL,
  method      TEXT NOT NULL,
  ip_address  TEXT,
  user_agent  TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_consent_audit_actor
  ON agent_consent_audit_log(actor_id, created_at DESC);

-- 4. Seed consent purposes
INSERT INTO agent_consent_purposes (id, title_ru, description, required, version) VALUES
  ('data_processing',
   'Обработка персональных данных',
   'Обработка ФИО, телефона, данных детей для предоставления образовательных услуг и консультаций через ИИ-ассистента Эврика.',
   TRUE, '1.0'),
  ('ai_memory',
   'Запоминание контекста',
   'ИИ-ассистент запоминает факты из диалогов (имя, класс, предпочтения) для персонализации будущих разговоров.',
   FALSE, '1.0'),
  ('crm_sync',
   'Передача данных в CRM',
   'Передача контактных данных и истории обращений в систему управления клиентами (amoCRM) для обработки заявок менеджерами.',
   FALSE, '1.0'),
  ('notifications',
   'Уведомления и напоминания',
   'Отправка напоминаний о незавершённых заявках, follow-up сообщений и информации об акциях.',
   FALSE, '1.0')
ON CONFLICT (id) DO NOTHING;
