"""Immutable strategy diagnostics, without portfolio/order/forecast tables."""

from alembic import op

revision = "0004a_evaluations"
down_revision = "0004_strategies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE strategy_evaluation (
            id UUID PRIMARY KEY,
            job_id UUID NOT NULL UNIQUE REFERENCES job(id) ON DELETE RESTRICT,
            strategy_version_id UUID NOT NULL REFERENCES strategy_version(id) ON DELETE RESTRICT,
            snapshot_id UUID NOT NULL REFERENCES dataset_snapshot(id) ON DELETE RESTRICT,
            as_of_session DATE NOT NULL, source_mode VARCHAR(32) NOT NULL,
            config_sha256 VARCHAR(64) NOT NULL CHECK (config_sha256 ~ '^[0-9a-f]{64}$'),
            snapshot_sha256 VARCHAR(64) NOT NULL CHECK (snapshot_sha256 ~ '^[0-9a-f]{64}$'),
            calendar_sha256 VARCHAR(64) NOT NULL CHECK (calendar_sha256 ~ '^[0-9a-f]{64}$'),
            engine_version VARCHAR(64) NOT NULL CHECK (engine_version ~ '^[0-9a-f]{64}$'),
            created_at TIMESTAMPTZ NOT NULL,
            CHECK (source_mode IN ('synthetic_fixture', 'research_market_data'))
        );
        CREATE TABLE strategy_evaluation_result (
            evaluation_id UUID PRIMARY KEY REFERENCES strategy_evaluation(id) ON DELETE RESTRICT,
            payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
            sha256 VARCHAR(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
            completed_at TIMESTAMPTZ NOT NULL, attempt_token UUID NOT NULL
        );
        CREATE FUNCTION reject_evaluation_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Diagnostic inputs and completed evidence are immutable';
        END $$;
        CREATE TRIGGER immutable_evaluation BEFORE UPDATE OR DELETE ON strategy_evaluation
            FOR EACH ROW EXECUTE FUNCTION reject_evaluation_mutation();
        CREATE TRIGGER immutable_evaluation_result
            BEFORE UPDATE OR DELETE ON strategy_evaluation_result
            FOR EACH ROW EXECUTE FUNCTION reject_evaluation_mutation();
    """)


def downgrade() -> None:
    raise RuntimeError("Diagnostic evidence is retained; restore a verified backup to downgrade")
