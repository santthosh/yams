"""Durable monthly review occurrences, request aliases and observed supervisor gaps."""

from alembic import op

revision = "0009_portfolio_reviews"
down_revision = "0008_recommendations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE portfolio_review_target (
            portfolio_id UUID PRIMARY KEY REFERENCES paper_portfolio(id) ON DELETE RESTRICT,
            last_explicit_review_cutoff TIMESTAMPTZ,
            last_handled_session DATE,
            next_session DATE, next_due_at TIMESTAMPTZ, next_window_end_at TIMESTAMPTZ,
            next_calendar_rows JSONB,
            last_observed_at TIMESTAMPTZ NOT NULL, last_clock_at TIMESTAMPTZ,
            status VARCHAR(32) NOT NULL, reason VARCHAR(100),
            CHECK ((next_session IS NULL)=(next_due_at IS NULL)),
            CHECK (next_window_end_at IS NULL OR next_window_end_at>next_due_at)
        );
        INSERT INTO portfolio_review_target(
            portfolio_id,last_explicit_review_cutoff,last_observed_at,status,reason
        )
        SELECT run.portfolio_id,MAX((run.payload->>'decision_cutoff_utc')::timestamptz),
               clock_timestamp(),'unobserved','NOT_YET_OBSERVED'
          FROM recommendation_run run
         WHERE run.payload->>'source_mode'='synthetic_fixture'
         GROUP BY run.portfolio_id;
        CREATE FUNCTION protect_review_target_clock() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP='DELETE' THEN
                RAISE EXCEPTION 'Durable review clock/checkpoints are retained';
            END IF;
            IF NEW.portfolio_id<>OLD.portfolio_id OR
               (OLD.last_explicit_review_cutoff IS NOT NULL AND
                (NEW.last_explicit_review_cutoff IS NULL OR
                 NEW.last_explicit_review_cutoff<OLD.last_explicit_review_cutoff)) OR
               (OLD.last_handled_session IS NOT NULL AND
                (NEW.last_handled_session IS NULL OR
                 NEW.last_handled_session<OLD.last_handled_session)) THEN
                RAISE EXCEPTION 'Review observations/checkpoints cannot rewind';
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER monotonic_review_target BEFORE UPDATE OR DELETE ON portfolio_review_target
            FOR EACH ROW EXECUTE FUNCTION protect_review_target_clock();
        CREATE TABLE portfolio_review_occurrence (
            id UUID PRIMARY KEY,
            portfolio_id UUID NOT NULL
                REFERENCES portfolio_review_target(portfolio_id) ON DELETE RESTRICT,
            decision_session DATE NOT NULL, due_at TIMESTAMPTZ NOT NULL,
            window_end_at TIMESTAMPTZ, calendar_rows JSONB NOT NULL,
            observed_snapshot_id UUID NOT NULL REFERENCES dataset_snapshot(id) ON DELETE RESTRICT,
            observed_snapshot_sha256 VARCHAR(64) NOT NULL
                CHECK(observed_snapshot_sha256 ~ '^[0-9a-f]{64}$'),
            observed_clock_at TIMESTAMPTZ NOT NULL, created_at TIMESTAMPTZ NOT NULL,
            outcome VARCHAR(24) NOT NULL
                CHECK(outcome IN ('waiting','admitted','missed','skipped')),
            reason VARCHAR(100), handled_at TIMESTAMPTZ, handled_clock_at TIMESTAMPTZ,
            recommendation_id UUID REFERENCES recommendation_run(id) ON DELETE RESTRICT,
            job_id UUID REFERENCES job(id) ON DELETE RESTRICT,
            UNIQUE(portfolio_id,decision_session),
            CHECK(jsonb_typeof(calendar_rows)='array'),
            CHECK(window_end_at IS NULL OR window_end_at>due_at),
            CHECK((outcome='waiting')=(handled_at IS NULL)),
            CHECK((outcome='waiting')=(handled_clock_at IS NULL)),
            CHECK((outcome='admitted')=(recommendation_id IS NOT NULL)),
            CHECK((outcome='admitted')=(job_id IS NOT NULL)),
            CHECK(outcome<>'waiting' OR reason IS NOT NULL)
        );
        CREATE INDEX ix_portfolio_review_recent
            ON portfolio_review_occurrence(portfolio_id,decision_session DESC);
        CREATE INDEX ix_portfolio_review_job
            ON portfolio_review_occurrence(job_id) WHERE job_id IS NOT NULL;
        CREATE TABLE recommendation_request_alias (
            portfolio_id UUID NOT NULL REFERENCES paper_portfolio(id) ON DELETE RESTRICT,
            idempotency_key UUID NOT NULL,
            recommendation_id UUID NOT NULL REFERENCES recommendation_run(id) ON DELETE RESTRICT,
            inputs_canonical_json TEXT NOT NULL CHECK(length(inputs_canonical_json)<=4096),
            created_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY(portfolio_id,idempotency_key)
        );
        CREATE INDEX ix_recommendation_review_context ON recommendation_run(
            portfolio_id,(payload->>'portfolio_revision'),(payload->>'snapshot_sha256'),
            (payload->>'engine_version'),created_at DESC
        );
        CREATE TABLE scheduler_observation (
            id INTEGER PRIMARY KEY CHECK(id=1),
            first_observed_at TIMESTAMPTZ NOT NULL, last_seen_at TIMESTAMPTZ NOT NULL,
            observer VARCHAR(100) NOT NULL, grace_seconds BIGINT NOT NULL CHECK(grace_seconds>=1),
            last_gap_start_at TIMESTAMPTZ, last_gap_end_at TIMESTAMPTZ,
            CHECK(last_seen_at>=first_observed_at),
            CHECK((last_gap_start_at IS NULL)=(last_gap_end_at IS NULL)),
            CHECK(last_gap_end_at IS NULL OR last_gap_end_at>=last_gap_start_at)
        );
        CREATE FUNCTION protect_review_occurrence() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP='DELETE' OR OLD.outcome<>'waiting' THEN
                RAISE EXCEPTION 'Handled review occurrences are immutable';
            END IF;
            IF (NEW.id,NEW.portfolio_id,NEW.decision_session,NEW.due_at,NEW.window_end_at,
                NEW.calendar_rows,NEW.observed_snapshot_id,NEW.observed_snapshot_sha256,
                NEW.observed_clock_at,NEW.created_at)
              IS DISTINCT FROM
               (OLD.id,OLD.portfolio_id,OLD.decision_session,OLD.due_at,OLD.window_end_at,
                OLD.calendar_rows,OLD.observed_snapshot_id,OLD.observed_snapshot_sha256,
                OLD.observed_clock_at,OLD.created_at) THEN
                RAISE EXCEPTION 'Original review occurrence timing/evidence is immutable';
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER immutable_handled_review
            BEFORE UPDATE OR DELETE ON portfolio_review_occurrence
            FOR EACH ROW EXECUTE FUNCTION protect_review_occurrence();
        CREATE TRIGGER immutable_recommendation_alias
            BEFORE UPDATE OR DELETE ON recommendation_request_alias
            FOR EACH ROW EXECUTE FUNCTION reject_recommendation_run_mutation();
    """)


def downgrade() -> None:
    raise RuntimeError(
        "Review/decision history is retained; restore a verified backup to downgrade"
    )
