# Migration ownership and startup

`python -m backend.persistence.bootstrap` supplies an existing SQLAlchemy connection to Alembic, following its [documented shared-transaction pattern](https://alembic.sqlalchemy.org/en/latest/cookbook.html#sharing-a-connection-across-one-or-more-programmatic-migration-commands). The connection owns the advisory lock, migration and seed transaction. The API does not migrate on import or startup; readiness verifies the database revision matches the single packaged head.

Add a reviewed Python revision to `versions/`, with `revision`, `down_revision`, `branch_labels`, `depends_on`, `upgrade()` and a non-destructive `downgrade()` policy. Follow the sequence and ownership in [ADR-004](../../../docs/adr/0004-portfolio-ledger.md); never rewrite a delivered revision or create tables owned by another feature. Update SQLAlchemy metadata alongside the migration and prove fresh upgrade plus already-populated upgrade in the isolated integration suite. A new revision must chain to the existing head; multiple heads are unsupported.

Revision `0001_workspace` creates only the singleton workspace. Bootstrap inserts defaults only when the singleton does not exist, preserving UUID/preferences across retries. Feature migrations must likewise preserve existing user data. Destructive rollback is unsupported; restore a verified backup into an isolated destination. No CLI downgrade or volume reset is part of normal startup.

Use the packaged entrypoint rather than an ad hoc URL in `alembic.ini`. Environment URLs, passwords and SQL parameters must never appear in diagnostics. Psycopg connections use explicit timeouts and SQLAlchemy hides parameters. Operational failures are returned as bounded readiness codes or a sanitized nonzero bootstrap exit.
