"""initial schema

Establishes the baseline revision for the ORM-managed tables.

`create_all` is idempotent, so applying this revision to an existing database is
safe (existing tables are left untouched).

Note: the raw `signals` / `component_feedback` tables are managed separately by
`tpt.data.database.init_db()`, which runs on application startup.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-10

"""
from __future__ import annotations

from alembic import op

from tpt.db.models import Base

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
