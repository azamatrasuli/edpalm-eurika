-- Sprint 5: Event logging for dashboard analytics
-- Run against Supabase PostgreSQL

CREATE TABLE IF NOT EXISTS agent_events (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID,
  actor_id        TEXT NOT NULL,
  channel         TEXT,
  agent_role      TEXT DEFAULT 'sales',
  event_type      TEXT NOT NULL,
  event_data      JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_events_type_created
  ON agent_events(event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_events_conversation
  ON agent_events(conversation_id);
CREATE INDEX IF NOT EXISTS idx_agent_events_created
  ON agent_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_events_channel
  ON agent_events(channel);
