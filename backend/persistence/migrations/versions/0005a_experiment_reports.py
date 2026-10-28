"""Final report registration shares the existing immutable experiment aggregate."""

from alembic import op

revision = "0005a_experiment_reports"
down_revision = "0005_experiments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE experiment_report (
            experiment_id UUID PRIMARY KEY REFERENCES experiment(id) ON DELETE RESTRICT,
            manifest_sha256 VARCHAR(64) NOT NULL CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
            attempt_token UUID NOT NULL,
            completed_at TIMESTAMPTZ NOT NULL
        );
        CREATE TRIGGER immutable_experiment_report BEFORE UPDATE OR DELETE ON experiment_report
            FOR EACH ROW EXECUTE FUNCTION reject_experiment_mutation();
        CREATE INDEX experiment_history ON experiment (created_at DESC, id DESC);
    """)


def downgrade() -> None:
    raise RuntimeError("Experiment reports are retained; restore a verified backup to downgrade")
