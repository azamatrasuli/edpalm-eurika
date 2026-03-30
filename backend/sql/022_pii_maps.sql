-- Migration 022: PII maps for tokenization (152-ФЗ compliance)
-- PiiMap per-actor: хранит маппинг ПДн ↔ токены в JSONB

CREATE TABLE IF NOT EXISTS agent_pii_maps (
    actor_id    TEXT        PRIMARY KEY,
    token_map   JSONB       NOT NULL DEFAULT '{}',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE agent_pii_maps IS
    'Per-actor PII tokenization maps. token_map: {"Иван": "[P]", "+79241234567": "[PH]"}. БД хранит оригинальные ПДн, токены — только для LLM.';

CREATE INDEX IF NOT EXISTS idx_pii_maps_updated_at ON agent_pii_maps (updated_at);
