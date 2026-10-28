"""Initial strategy registry; versions cannot be overwritten by future publishers."""

from alembic import op

revision = "0004_strategies"
down_revision = "0003_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE strategy (
            id UUID PRIMARY KEY,
            workspace_id UUID NOT NULL REFERENCES local_workspace(id) ON DELETE RESTRICT,
            name VARCHAR(120) NOT NULL CHECK (length(name) > 0),
            name_key VARCHAR(360) NOT NULL CHECK (length(name_key) > 0),
            template_key VARCHAR(100), created_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT uq_strategy_name UNIQUE (workspace_id, name_key),
            CONSTRAINT uq_strategy_template UNIQUE (workspace_id, template_key)
        );
        CREATE TABLE strategy_version (
            id UUID PRIMARY KEY,
            strategy_id UUID NOT NULL REFERENCES strategy(id) ON DELETE RESTRICT,
            version INTEGER NOT NULL CHECK (version >= 1),
            status VARCHAR(20) NOT NULL CHECK (status = 'published'),
            config JSONB NOT NULL CHECK (jsonb_typeof(config) = 'object'),
            config_sha256 VARCHAR(64) NOT NULL CHECK (config_sha256 ~ '^[0-9a-f]{64}$'),
            published_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT uq_strategy_version UNIQUE (strategy_id, version)
        );
        CREATE FUNCTION reject_strategy_version_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Published strategy versions are immutable';
        END $$;
        CREATE TRIGGER immutable_strategy_version BEFORE UPDATE OR DELETE ON strategy_version
            FOR EACH ROW EXECUTE FUNCTION reject_strategy_version_mutation();
    """)


def downgrade() -> None:
    raise RuntimeError("Strategy history is retained; restore a verified backup to downgrade")
