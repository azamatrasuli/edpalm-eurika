-- ============================================================================
-- 018: Data requests — export & deletion tracking (GDPR / ФЗ-152)
-- ============================================================================

CREATE TABLE IF NOT EXISTS agent_data_requests (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_id        TEXT NOT NULL,
  request_type    TEXT NOT NULL CHECK (request_type IN ('export', 'deletion')),
  status          TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'processing', 'ready', 'completed', 'cancelled', 'failed')),
  download_url    TEXT,
  export_data     JSONB,
  execute_after   TIMESTAMPTZ,
  completed_at    TIMESTAMPTZ,
  reason          TEXT,
  ip_address      TEXT,
  user_agent      TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_data_requests_actor
  ON agent_data_requests(actor_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_data_requests_pending_deletion
  ON agent_data_requests(status, execute_after)
  WHERE request_type = 'deletion' AND status = 'pending';
