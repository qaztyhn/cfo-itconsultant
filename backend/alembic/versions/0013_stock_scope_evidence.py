"""0013_stock_scope_evidence

DEC-OWNER-20261109 S1-S5 (stock scope and independence evidence persistence). Proposed names, subject to
review in the PR (docs/05 §6.1):

- ref.stock_admin_grant: explicit, market-specific, revocable Admin grants (capability scope | evidence);
- ops.stock_scope_version: market-wide immutable SKU scope + expected warehouses, author <> approver,
  effective from approval;
- ops.stock_independence_evidence: Warehouse Manager evidence, separately approved, <= 30 days;
- ops.stock_write_run: append-only binding of an accepted/rejected stock write to scope/evidence versions
  and the trusted Source batch `as_of`.
No stock writer is enabled by this migration.
Owner: Dev 1 (with Dev 2 review).
"""

from alembic import op

revision = "0013"
down_revision = "0012"

TS = "created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()"
TABLES = (
    ("ref", "stock_admin_grant"),
    ("ops", "stock_scope_version"),
    ("ops", "stock_independence_evidence"),
    ("ops", "stock_write_run"),
)

UPGRADE: tuple[str, ...] = (
    f"""CREATE TABLE ref.stock_admin_grant (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  market_id smallint NOT NULL REFERENCES ref.market(id),
  user_id bigint NOT NULL REFERENCES ref.app_user(id),
  capability text NOT NULL CHECK (capability IN ('scope','evidence')),
  valid_from timestamptz NOT NULL, valid_to timestamptz,
  granted_by bigint NOT NULL REFERENCES ref.app_user(id), reason_text text NOT NULL CHECK (btrim(reason_text) <> ''),
  revoked_at timestamptz, revoked_by bigint REFERENCES ref.app_user(id), revoke_reason text,
  {TS},
  CONSTRAINT ck_grant_window CHECK (valid_to IS NULL OR valid_to > valid_from),
  CONSTRAINT ck_grant_not_self CHECK (granted_by <> user_id),
  CONSTRAINT ck_grant_revoked CHECK ((revoked_at IS NULL) = (revoked_by IS NULL)
    AND (revoked_at IS NULL OR btrim(coalesce(revoke_reason, '')) <> ''))
)""",
    "CREATE INDEX ix_stock_grant_active ON ref.stock_admin_grant (market_id, user_id, capability)",
    f"""CREATE TABLE ops.stock_scope_version (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  market_id smallint NOT NULL REFERENCES ref.market(id), version int NOT NULL,
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','rejected','superseded')),
  skus text[] NOT NULL CHECK (cardinality(skus) > 0),
  warehouse_ids bigint[] NOT NULL CHECK (cardinality(warehouse_ids) > 0),
  reason_text text NOT NULL CHECK (btrim(reason_text) <> ''),
  created_by bigint NOT NULL REFERENCES ref.app_user(id),
  approved_by bigint REFERENCES ref.app_user(id), approved_at timestamptz,
  effective_from timestamptz, superseded_at timestamptz,
  {TS},
  UNIQUE (market_id, version),
  CONSTRAINT ck_scope_author_not_approver CHECK (approved_by IS NULL OR approved_by <> created_by),
  CONSTRAINT ck_scope_approval CHECK (
    (status IN ('approved','superseded')) = (approved_by IS NOT NULL AND approved_at IS NOT NULL
                                             AND effective_from IS NOT NULL)),
  CONSTRAINT ck_scope_not_retroactive CHECK (effective_from IS NULL OR effective_from >= approved_at),
  CONSTRAINT ck_scope_superseded CHECK ((status = 'superseded') = (superseded_at IS NOT NULL))
)""",
    "CREATE UNIQUE INDEX ux_stock_scope_one_approved ON ops.stock_scope_version (market_id) "
    "WHERE status = 'approved'",
    f"""CREATE TABLE ops.stock_independence_evidence (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  market_id smallint NOT NULL REFERENCES ref.market(id),
  warehouse_id bigint NOT NULL REFERENCES ref.location(id), version int NOT NULL,
  scope_version_id bigint NOT NULL REFERENCES ops.stock_scope_version(id),
  local_skus text[] NOT NULL CHECK (cardinality(local_skus) >= 2),
  mapping_fingerprint text NOT NULL CHECK (btrim(mapping_fingerprint) <> ''),
  evidence_ref text NOT NULL CHECK (btrim(evidence_ref) <> ''),
  status text NOT NULL DEFAULT 'submitted' CHECK (status IN ('submitted','approved','rejected','revoked')),
  submitted_by bigint NOT NULL REFERENCES ref.app_user(id),
  approved_by bigint REFERENCES ref.app_user(id), approved_at timestamptz,
  valid_from timestamptz, valid_to timestamptz,
  revoked_at timestamptz, revoke_reason text,
  {TS},
  UNIQUE (market_id, warehouse_id, version),
  CONSTRAINT ck_evidence_submitter_not_approver CHECK (approved_by IS NULL OR approved_by <> submitted_by),
  CONSTRAINT ck_evidence_approved CHECK (
    (status IN ('approved','revoked')) = (approved_by IS NOT NULL AND approved_at IS NOT NULL
                                          AND valid_from IS NOT NULL AND valid_to IS NOT NULL)),
  CONSTRAINT ck_evidence_max_30_days CHECK (
    valid_from IS NULL OR (valid_to > valid_from AND valid_to <= valid_from + interval '30 days')),
  CONSTRAINT ck_evidence_revoked CHECK ((status = 'revoked') = (revoked_at IS NOT NULL))
)""",
    f"""CREATE TABLE ops.stock_write_run (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  market_id smallint NOT NULL REFERENCES ref.market(id),
  source_batch_id bigint NOT NULL CHECK (source_batch_id > 0), as_of timestamptz NOT NULL,
  scope_version_id bigint REFERENCES ops.stock_scope_version(id),
  evidence_ids bigint[] NOT NULL DEFAULT '{{}}',
  expected_rows int NOT NULL CHECK (expected_rows >= 0), recorded_rows int NOT NULL CHECK (recorded_rows >= 0),
  status text NOT NULL CHECK (status IN ('accepted','rejected')),
  reject_code text,
  {TS},
  UNIQUE (market_id, source_batch_id),
  CONSTRAINT ck_write_run_status CHECK (
    (status = 'accepted' AND scope_version_id IS NOT NULL AND reject_code IS NULL
       AND recorded_rows = expected_rows)
    OR (status = 'rejected' AND reject_code IS NOT NULL AND recorded_rows = 0))
)""",
    # approved/superseded scope versions are immutable except the supersede transition
    """CREATE FUNCTION ops.guard_stock_scope_version() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'draft' THEN
      RAISE EXCEPTION 'stock_scope_version history is immutable (delete)'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF OLD.status IN ('approved','superseded','rejected') THEN
    IF NEW.market_id IS DISTINCT FROM OLD.market_id OR NEW.version IS DISTINCT FROM OLD.version
       OR NEW.skus IS DISTINCT FROM OLD.skus OR NEW.warehouse_ids IS DISTINCT FROM OLD.warehouse_ids
       OR NEW.reason_text IS DISTINCT FROM OLD.reason_text OR NEW.created_by IS DISTINCT FROM OLD.created_by
       OR NEW.approved_by IS DISTINCT FROM OLD.approved_by OR NEW.approved_at IS DISTINCT FROM OLD.approved_at
       OR NEW.effective_from IS DISTINCT FROM OLD.effective_from
       OR NOT (NEW.status = OLD.status OR (OLD.status = 'approved' AND NEW.status = 'superseded')) THEN
      RAISE EXCEPTION 'stock_scope_version is immutable after the decision'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql""",
    "CREATE TRIGGER trg_guard_stock_scope BEFORE UPDATE OR DELETE ON ops.stock_scope_version "
    "FOR EACH ROW EXECUTE FUNCTION ops.guard_stock_scope_version()",
    # evidence: identity/content fixed; only the decision fields move forward
    """CREATE FUNCTION ops.guard_stock_evidence() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'stock_independence_evidence history is immutable (delete)'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.market_id IS DISTINCT FROM OLD.market_id OR NEW.warehouse_id IS DISTINCT FROM OLD.warehouse_id
     OR NEW.version IS DISTINCT FROM OLD.version OR NEW.scope_version_id IS DISTINCT FROM OLD.scope_version_id
     OR NEW.local_skus IS DISTINCT FROM OLD.local_skus
     OR NEW.mapping_fingerprint IS DISTINCT FROM OLD.mapping_fingerprint
     OR NEW.evidence_ref IS DISTINCT FROM OLD.evidence_ref OR NEW.submitted_by IS DISTINCT FROM OLD.submitted_by
     OR (OLD.status IN ('approved','revoked') AND (NEW.approved_by IS DISTINCT FROM OLD.approved_by
         OR NEW.approved_at IS DISTINCT FROM OLD.approved_at OR NEW.valid_from IS DISTINCT FROM OLD.valid_from
         OR NEW.valid_to IS DISTINCT FROM OLD.valid_to))
     OR OLD.status IN ('rejected','revoked')
     OR (OLD.status = 'approved' AND NEW.status NOT IN ('approved','revoked'))
     OR (OLD.status = 'submitted' AND NEW.status NOT IN ('submitted','approved','rejected')) THEN
    RAISE EXCEPTION 'stock_independence_evidence is immutable after the decision'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql""",
    "CREATE TRIGGER trg_guard_stock_evidence BEFORE UPDATE OR DELETE ON ops.stock_independence_evidence "
    "FOR EACH ROW EXECUTE FUNCTION ops.guard_stock_evidence()",
    "CREATE TRIGGER trg_forbid_stock_write_run BEFORE UPDATE OR DELETE ON ops.stock_write_run "
    "FOR EACH ROW EXECUTE FUNCTION audit.forbid_mutation()",
    *(
        f"CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON {schema}.{table} "
        "FOR EACH ROW EXECUTE FUNCTION audit.set_updated_at()"
        for schema, table in TABLES
    ),
)

DOWNGRADE: tuple[str, ...] = (
    "DROP TABLE ops.stock_write_run",
    "DROP TABLE ops.stock_independence_evidence",
    "DROP TABLE ops.stock_scope_version",
    "DROP TABLE ref.stock_admin_grant",
    "DROP FUNCTION ops.guard_stock_evidence()",
    "DROP FUNCTION ops.guard_stock_scope_version()",
)


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
