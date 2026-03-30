-- Migration 023: LLM audit log + encryption columns (Phase 13, 152-ФЗ)

-- LLM audit log: tamper-evident record of every OpenAI API call
CREATE TABLE IF NOT EXISTS agent_llm_audit_log (
    id                BIGSERIAL   PRIMARY KEY,
    actor_id          TEXT        NOT NULL,
    agent_role        TEXT        NOT NULL DEFAULT 'unknown',
    model             TEXT        NOT NULL,
    prompt_tokens     INT,
    completion_tokens INT,
    pii_proxy_active  BOOLEAN     NOT NULL DEFAULT FALSE,
    called_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    hmac              TEXT        NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_audit_log_actor ON agent_llm_audit_log (actor_id, called_at DESC);

COMMENT ON TABLE agent_llm_audit_log IS
    'Tamper-evident audit of LLM calls. HMAC = SHA256(actor_id|model|called_at|pii_proxy_active).';

-- Note: Column-level encryption of agent_user_profiles and agent_pii_maps is handled
-- at the application layer (app/services/crypto.py AES-256-GCM).
-- Existing columns remain TEXT/JSONB; the application encrypts before INSERT
-- and decrypts after SELECT when PII_ENCRYPTION_KEY is configured.
