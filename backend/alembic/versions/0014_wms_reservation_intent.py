"""0014: durable WMS reservation intent/ACK ledger (no outbound WMS enablement)."""

from alembic import op

revision = "0014"
down_revision = "0013"


def upgrade() -> None:
    op.execute("""
CREATE TABLE ops.wms_reservation_intent (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  market_id smallint NOT NULL REFERENCES ref.market(id),
  order_id bigint NOT NULL REFERENCES ops.customer_order(id),
  plan_id bigint NOT NULL REFERENCES plan.fulfilment_plan(id),
  order_version integer NOT NULL CHECK (order_version > 0),
  source_version integer NOT NULL CHECK (source_version > 0),
  request_key text NOT NULL UNIQUE CHECK (btrim(request_key) <> ''),
  request_payload jsonb NOT NULL,
  request_digest text NOT NULL CHECK (length(request_digest) = 64),
  status text NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','unknown','acked','refreshed','rejected','released')),
  reservation_id text,
  ack_revision text,
  ack_payload jsonb,
  reflected_in_batch_id bigint,
  refreshed_batch_id bigint,
  is_synthetic boolean NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (order_id),
  CONSTRAINT ck_wms_ack_complete CHECK (
    (status IN ('acked','refreshed') AND reservation_id IS NOT NULL
       AND ack_revision IS NOT NULL AND ack_payload IS NOT NULL)
    OR status NOT IN ('acked','refreshed')
  ),
  CONSTRAINT ck_wms_refreshed CHECK (
    status <> 'refreshed' OR
      (reflected_in_batch_id IS NOT NULL AND refreshed_batch_id IS NOT NULL
       AND refreshed_batch_id >= reflected_in_batch_id)
  )
)
""")
    op.execute("CREATE INDEX ix_wms_intent_market_status ON ops.wms_reservation_intent (market_id,status)")
    op.execute(
        "CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON ops.wms_reservation_intent "
        "FOR EACH ROW EXECUTE FUNCTION audit.set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TABLE ops.wms_reservation_intent")
