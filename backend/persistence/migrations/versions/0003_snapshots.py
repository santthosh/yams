"""Immutable dataset metadata and separate publication/current references."""

from alembic import op

revision = "0003_snapshots"
down_revision = "0002_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE dataset_snapshot (
            id UUID PRIMARY KEY, manifest_hash VARCHAR(64) NOT NULL UNIQUE,
            manifest JSONB NOT NULL, source_mode VARCHAR(32) NOT NULL,
            quality VARCHAR(32) NOT NULL, registered_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT ck_snapshot_digest CHECK (manifest_hash ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_snapshot_source_mode CHECK (
                source_mode IN ('synthetic_fixture','research_market_data')),
            CONSTRAINT ck_snapshot_quality CHECK (
                quality IN ('usable','usable_with_warnings','blocked'))
        );
        CREATE TABLE snapshot_artifact (
            snapshot_id UUID NOT NULL REFERENCES dataset_snapshot(id) ON DELETE RESTRICT,
            path VARCHAR(512) NOT NULL, sha256 VARCHAR(64) NOT NULL,
            size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
            PRIMARY KEY(snapshot_id, path), CHECK (sha256 ~ '^[0-9a-f]{64}$')
        );
        CREATE TABLE snapshot_publication (
            job_id UUID PRIMARY KEY REFERENCES job(id) ON DELETE RESTRICT,
            snapshot_id UUID NOT NULL REFERENCES dataset_snapshot(id) ON DELETE RESTRICT,
            attempt_token UUID NOT NULL, published_at TIMESTAMPTZ NOT NULL
        );
        CREATE TABLE current_snapshot (
            source_mode VARCHAR(32) PRIMARY KEY,
            snapshot_id UUID NOT NULL REFERENCES dataset_snapshot(id) ON DELETE RESTRICT,
            publication_job_id UUID NOT NULL REFERENCES snapshot_publication(job_id)
                ON DELETE RESTRICT
        );
        CREATE FUNCTION reject_snapshot_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Published snapshot metadata is immutable';
        END $$;
        CREATE TRIGGER immutable_snapshot BEFORE UPDATE OR DELETE ON dataset_snapshot
            FOR EACH ROW EXECUTE FUNCTION reject_snapshot_mutation();
        CREATE TRIGGER immutable_snapshot_artifact BEFORE UPDATE OR DELETE ON snapshot_artifact
            FOR EACH ROW EXECUTE FUNCTION reject_snapshot_mutation();
        CREATE TRIGGER immutable_snapshot_publication
            BEFORE UPDATE OR DELETE ON snapshot_publication
            FOR EACH ROW EXECUTE FUNCTION reject_snapshot_mutation();
    """)


def downgrade() -> None:
    raise RuntimeError("Snapshot history is retained; restore a verified backup to downgrade")
