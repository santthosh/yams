"""Immutable forecast inputs/artifacts; no account, recommendation or fill is seeded."""

from alembic import op

revision = "0007_forecasts"
down_revision = "0006_paper_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE forecast (
            id UUID PRIMARY KEY,
            job_id UUID NOT NULL UNIQUE REFERENCES job(id) ON DELETE RESTRICT,
            portfolio_id UUID NOT NULL REFERENCES paper_portfolio(id) ON DELETE RESTRICT,
            portfolio_revision BIGINT NOT NULL CHECK (portfolio_revision >= 1),
            strategy_version_id UUID NOT NULL REFERENCES strategy_version(id) ON DELETE RESTRICT,
            snapshot_id UUID NOT NULL REFERENCES dataset_snapshot(id) ON DELETE RESTRICT,
            payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
            created_at TIMESTAMPTZ NOT NULL
        );
        CREATE TABLE forecast_artifact (
            forecast_id UUID PRIMARY KEY REFERENCES forecast(id) ON DELETE RESTRICT,
            manifest_sha256 VARCHAR(64) NOT NULL CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
            attempt_token UUID NOT NULL,
            completed_at TIMESTAMPTZ NOT NULL
        );
        CREATE FUNCTION reject_forecast_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Forecast inputs and sealed evidence are immutable';
        END $$;
        CREATE TRIGGER immutable_forecast BEFORE UPDATE OR DELETE ON forecast
            FOR EACH ROW EXECUTE FUNCTION reject_forecast_mutation();
        CREATE TRIGGER immutable_forecast_artifact BEFORE UPDATE OR DELETE ON forecast_artifact
            FOR EACH ROW EXECUTE FUNCTION reject_forecast_mutation();
    """)


def downgrade() -> None:
    raise RuntimeError("Forecast evidence is retained; restore a verified backup to downgrade")
