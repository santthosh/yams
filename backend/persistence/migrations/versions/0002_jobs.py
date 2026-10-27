"""Durable fenced jobs, attempts and diagnostic schedule/effect identities."""

from alembic import op

revision = "0002_jobs"
down_revision = "0001_workspace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE schedule (
            id UUID PRIMARY KEY, version INTEGER NOT NULL, target VARCHAR(160) NOT NULL,
            kind VARCHAR(64) NOT NULL, payload JSONB NOT NULL, limits JSONB NOT NULL,
            interval_seconds INTEGER NOT NULL, next_due_at TIMESTAMPTZ NOT NULL,
            enabled BOOLEAN NOT NULL,
            CONSTRAINT ck_schedule_bounds CHECK (version >= 1 AND interval_seconds >= 5)
        );
        CREATE TABLE job (
            id UUID PRIMARY KEY, schema_version INTEGER NOT NULL CHECK (schema_version = 1),
            kind VARCHAR(64) NOT NULL, payload JSONB NOT NULL, payload_hash VARCHAR(64) NOT NULL,
            request_hash VARCHAR(64) NOT NULL, idempotency_key UUID NOT NULL UNIQUE,
            source_mode VARCHAR(32) NOT NULL, correlation_id UUID NOT NULL,
            status VARCHAR(32) NOT NULL, created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL, scheduled_at TIMESTAMPTZ,
            available_at TIMESTAMPTZ NOT NULL, attempts INTEGER NOT NULL,
            max_attempts INTEGER NOT NULL, progress DOUBLE PRECISION NOT NULL,
            cancel_requested_at TIMESTAMPTZ, lease_owner VARCHAR(128), lease_token UUID,
            lease_expires_at TIMESTAMPTZ, heartbeat_at TIMESTAMPTZ, attempt_deadline TIMESTAMPTZ,
            limits JSONB NOT NULL, result JSONB, error JSONB,
            schedule_id UUID REFERENCES schedule(id) ON DELETE RESTRICT,
            schedule_version INTEGER, occurrence_at TIMESTAMPTZ, target VARCHAR(160),
            CONSTRAINT uq_job_occurrence UNIQUE (schedule_id, schedule_version, occurrence_at),
            CONSTRAINT ck_job_attempts CHECK (
                attempts >= 0 AND attempts <= max_attempts AND max_attempts BETWEEN 1 AND 3),
            CONSTRAINT ck_job_progress CHECK (progress >= 0 AND progress <= 100),
            CONSTRAINT ck_job_status CHECK (
                status IN ('queued','running','cancel_requested','completed','failed','cancelled')),
            CONSTRAINT ck_job_result CHECK ((status = 'completed') = (result IS NOT NULL)),
            CONSTRAINT ck_job_error CHECK ((status = 'failed') = (error IS NOT NULL))
        );
        CREATE INDEX ix_job_due ON job(status, available_at, created_at, id);
        CREATE TABLE job_attempt (
            job_id UUID NOT NULL REFERENCES job(id) ON DELETE RESTRICT,
            number INTEGER NOT NULL, token UUID NOT NULL UNIQUE, started_at TIMESTAMPTZ NOT NULL,
            ended_at TIMESTAMPTZ, outcome VARCHAR(32), diagnostics JSONB NOT NULL,
            PRIMARY KEY(job_id, number)
        );
        CREATE TABLE job_diagnostic_effect (
            job_id UUID PRIMARY KEY REFERENCES job(id) ON DELETE RESTRICT,
            value BIGINT NOT NULL, created_at TIMESTAMPTZ NOT NULL
        );
        CREATE FUNCTION guard_schedule_inputs() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF ROW(NEW.id, NEW.version, NEW.target, NEW.kind, NEW.payload, NEW.limits,
                   NEW.interval_seconds) IS DISTINCT FROM
               ROW(OLD.id, OLD.version, OLD.target, OLD.kind, OLD.payload, OLD.limits,
                   OLD.interval_seconds) THEN
                RAISE EXCEPTION 'Schedule inputs are immutable; create a new schedule';
            END IF;
            IF NEW.next_due_at < OLD.next_due_at THEN
                RAISE EXCEPTION 'Schedule cursor cannot move backwards';
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER immutable_schedule_inputs BEFORE UPDATE ON schedule
            FOR EACH ROW EXECUTE FUNCTION guard_schedule_inputs();
        CREATE FUNCTION guard_job_inputs() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF ROW(NEW.id, NEW.schema_version, NEW.kind, NEW.payload, NEW.payload_hash,
                   NEW.request_hash, NEW.idempotency_key, NEW.source_mode, NEW.correlation_id,
                   NEW.created_at, NEW.scheduled_at, NEW.max_attempts, NEW.limits,
                   NEW.schedule_id, NEW.schedule_version, NEW.occurrence_at, NEW.target)
               IS DISTINCT FROM
               ROW(OLD.id, OLD.schema_version, OLD.kind, OLD.payload, OLD.payload_hash,
                   OLD.request_hash, OLD.idempotency_key, OLD.source_mode, OLD.correlation_id,
                   OLD.created_at, OLD.scheduled_at, OLD.max_attempts, OLD.limits,
                   OLD.schedule_id, OLD.schedule_version, OLD.occurrence_at, OLD.target) THEN
                RAISE EXCEPTION 'Job inputs are immutable';
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER immutable_job_inputs BEFORE UPDATE ON job
            FOR EACH ROW EXECUTE FUNCTION guard_job_inputs();
    """)


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is unsupported; restore a verified backup")
