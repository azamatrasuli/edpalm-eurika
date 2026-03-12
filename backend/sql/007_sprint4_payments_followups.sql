-- Sprint 4: Payment orders and follow-up chain

CREATE TABLE IF NOT EXISTS agent_payment_orders (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL,
  actor_id        TEXT NOT NULL,
  dms_order_uuid  TEXT NOT NULL,
  dms_contact_id  INT,
  product_name    TEXT,
  product_uuid    TEXT,
  amount_kopecks  BIGINT NOT NULL,
  payment_url     TEXT NOT NULL,
  pay_type        INT NOT NULL DEFAULT 1,
  status          TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'paid', 'expired', 'cancelled')),
  amocrm_lead_id  BIGINT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  paid_at         TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_payment_orders_pending
  ON agent_payment_orders(status) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_payment_orders_actor
  ON agent_payment_orders(actor_id);

CREATE TABLE IF NOT EXISTS agent_followup_chain (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL,
  actor_id        TEXT NOT NULL,
  payment_order_id UUID REFERENCES agent_payment_orders(id) ON DELETE SET NULL,
  step            INT NOT NULL DEFAULT 1,
  status          TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'sent', 'cancelled', 'escalated')),
  next_fire_at    TIMESTAMPTZ NOT NULL,
  sent_at         TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_followup_pending
  ON agent_followup_chain(status, next_fire_at) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_followup_conversation
  ON agent_followup_chain(conversation_id);
