"""0016: Remove channel preference and outbox channel (DEC-R3-02 clarification)."""

from alembic import op

revision = "0016"
down_revision = "0015"


def upgrade() -> None:
    op.execute("ALTER TABLE ops.notification DROP CONSTRAINT ck_notification_email_only_r3")
    op.execute("ALTER TABLE ops.notification ALTER COLUMN recipient DROP NOT NULL")
    op.execute("""UPDATE ops.notification
        SET recipient = NULL,
            status = CASE WHEN status IN ('draft','queued') THEN 'suppressed' ELSE status END,
            suppressed_reason = CASE
                WHEN status IN ('draft','queued') THEN 'legacy_sms'
                ELSE suppressed_reason
            END
        WHERE channel = 'sms_sim'""")
    op.execute("ALTER TABLE ops.notification DROP COLUMN channel")
    op.execute("ALTER TABLE ref.customer DROP COLUMN preferred_channel")


def downgrade() -> None:
    # The old channel preferences and SMS destinations cannot be recovered.
    op.execute("""ALTER TABLE ref.customer ADD COLUMN preferred_channel ref.notify_channel
        NOT NULL DEFAULT 'email'""")
    op.execute("""ALTER TABLE ops.notification ADD COLUMN channel ref.notify_channel
        NOT NULL DEFAULT 'email'""")
    op.execute("ALTER TABLE ops.notification ALTER COLUMN channel DROP DEFAULT")
    op.execute("""UPDATE ops.notification
        SET status = 'suppressed', suppressed_reason = COALESCE(suppressed_reason, 'SKIPPED_NO_CHANNEL')
        WHERE recipient IS NULL AND status IN ('draft','queued')""")
    op.execute("""UPDATE ops.notification SET recipient = 'suppressed@cfo.test'
        WHERE recipient IS NULL""")
    op.execute("ALTER TABLE ops.notification ALTER COLUMN recipient SET NOT NULL")
    op.execute("""ALTER TABLE ops.notification ADD CONSTRAINT ck_notification_email_only_r3
        CHECK (channel = 'email') NOT VALID""")
