"""Immutable recommendation computation linkage; existing identity/content retained."""

from alembic import op

revision = "0008_recommendations"
down_revision = "0007_forecasts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE recommendation_run (
            id UUID PRIMARY KEY,
            job_id UUID NOT NULL UNIQUE REFERENCES job(id) ON DELETE RESTRICT,
            portfolio_id UUID NOT NULL REFERENCES paper_portfolio(id) ON DELETE RESTRICT,
            payload JSONB NOT NULL CHECK (jsonb_typeof(payload)='object'),
            created_at TIMESTAMPTZ NOT NULL
        );
        CREATE TABLE recommendation_publication (
            recommendation_id UUID PRIMARY KEY REFERENCES recommendation_run(id) ON DELETE RESTRICT,
            FOREIGN KEY (recommendation_id) REFERENCES recommendation(id) ON DELETE RESTRICT,
            forecast_id UUID NOT NULL UNIQUE REFERENCES forecast(id) ON DELETE RESTRICT,
            attempt_token UUID NOT NULL,
            completed_at TIMESTAMPTZ NOT NULL
        );
        CREATE FUNCTION reject_recommendation_run_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Recommendation computation and publication are immutable';
        END $$;
        CREATE TRIGGER immutable_recommendation_run BEFORE UPDATE OR DELETE ON recommendation_run
            FOR EACH ROW EXECUTE FUNCTION reject_recommendation_run_mutation();
        CREATE TRIGGER immutable_recommendation_publication BEFORE UPDATE OR DELETE
            ON recommendation_publication FOR EACH ROW
            EXECUTE FUNCTION reject_recommendation_run_mutation();
    """)


def downgrade() -> None:
    raise RuntimeError(
        "Recommendation evidence is retained; restore a verified backup to downgrade"
    )
