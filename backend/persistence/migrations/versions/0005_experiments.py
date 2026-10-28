"""Immutable experiment/core evidence; final report composition follows in #40/#41."""

from alembic import op

revision = "0005_experiments"
down_revision = "0004a_evaluations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE experiment (
            id UUID PRIMARY KEY,
            job_id UUID NOT NULL UNIQUE REFERENCES job(id) ON DELETE RESTRICT,
            strategy_version_id UUID NOT NULL REFERENCES strategy_version(id) ON DELETE RESTRICT,
            snapshot_id UUID NOT NULL REFERENCES dataset_snapshot(id) ON DELETE RESTRICT,
            payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
            created_at TIMESTAMPTZ NOT NULL
        );
        CREATE TABLE experiment_core (
            experiment_id UUID PRIMARY KEY REFERENCES experiment(id) ON DELETE RESTRICT,
            manifest_sha256 VARCHAR(64) NOT NULL CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
            attempt_token UUID NOT NULL,
            completed_at TIMESTAMPTZ NOT NULL
        );
        CREATE FUNCTION reject_experiment_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Experiment inputs and sealed core identity are immutable';
        END $$;
        CREATE TRIGGER immutable_experiment BEFORE UPDATE OR DELETE ON experiment
            FOR EACH ROW EXECUTE FUNCTION reject_experiment_mutation();
        CREATE TRIGGER immutable_experiment_core BEFORE UPDATE OR DELETE ON experiment_core
            FOR EACH ROW EXECUTE FUNCTION reject_experiment_mutation();
    """)


def downgrade() -> None:
    raise RuntimeError("Experiment evidence is retained; restore a verified backup to downgrade")
