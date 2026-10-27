"""Migration connection is supplied by the bounded bootstrap transaction."""

from alembic import context
from sqlalchemy import Connection

from backend.persistence.models.workspace import Base

connection = context.config.attributes.get("connection")
if not isinstance(connection, Connection):
    raise RuntimeError("Use python -m backend.persistence.bootstrap")
context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
with context.begin_transaction():
    context.run_migrations()
