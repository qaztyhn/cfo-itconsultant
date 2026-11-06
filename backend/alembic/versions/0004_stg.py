"""0004_stg

Schema stg: sync_run, sync_reject, sync_checkpoint (05 mục 5).

Cột chung created_at/updated_at (05 mục 1, ASM-001) có ở mọi bảng; các mốc nghiệp vụ (started_at,
finished_at, data_as_of, last_updated_since) giữ nguyên. Trigger set_updated_at gắn ở 0007.

Nguồn sự thật: docs/05_Database_Design.md. Không đổi tên bảng/cột/enum (09 mục 6).
Owner: Dev 1 (luồng A).
"""

from alembic import op

revision = "0004"
down_revision = "0003"

TS = "created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()"

UPGRADE: tuple[str, ...] = (
    f"""CREATE TABLE stg.sync_run (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  market_id smallint NOT NULL REFERENCES ref.market(id),
  entity text NOT NULL CHECK (entity IN ('orders','customers','products','stock','inbound','fleet')),
  kind text NOT NULL DEFAULT 'api' CHECK (kind IN ('api','csv')),
  checkpoint_from timestamptz, checkpoint_to timestamptz,
  file_name text, file_sha256 text,
  started_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
  status text NOT NULL DEFAULT 'running' CHECK (status IN ('running','ok','partial','failed')),
  rows_in int NOT NULL DEFAULT 0, rows_ok int NOT NULL DEFAULT 0, rows_rejected int NOT NULL DEFAULT 0,
  data_as_of timestamptz,
  error text,
  {TS}
)""",
    "CREATE UNIQUE INDEX ux_sync_file ON stg.sync_run (market_id, entity, file_sha256) "
    "WHERE file_sha256 IS NOT NULL AND status IN ('ok','partial')",
    f"""CREATE TABLE stg.sync_reject (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id bigint NOT NULL REFERENCES stg.sync_run(id),
  external_key text, reason_code text NOT NULL,
  reason text, raw jsonb,
  {TS}
)""",
    f"""CREATE TABLE stg.sync_checkpoint (
  market_id smallint NOT NULL REFERENCES ref.market(id),
  entity text NOT NULL, last_updated_since timestamptz NOT NULL,
  {TS},
  PRIMARY KEY (market_id, entity)
)""",
)

DOWNGRADE: tuple[str, ...] = (
    "DROP TABLE stg.sync_checkpoint",
    "DROP TABLE stg.sync_reject",
    "DROP TABLE stg.sync_run",
)


def upgrade() -> None:
    """Tạo bảng stg theo 05 mục 5."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Gỡ đúng thứ tự ngược lại."""
    for statement in DOWNGRADE:
        op.execute(statement)
