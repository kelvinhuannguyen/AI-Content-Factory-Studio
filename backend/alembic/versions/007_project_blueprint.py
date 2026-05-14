"""Project blueprint_r2_key — Final Assembler output

Revision ID: 007
Revises: 006
Create Date: 2026-05-14
"""
from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None

_UPGRADE_STATEMENTS = [
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS blueprint_r2_key VARCHAR(1000)",
]

_DOWNGRADE_STATEMENTS = [
    "ALTER TABLE projects DROP COLUMN IF EXISTS blueprint_r2_key",
]


def upgrade() -> None:
    for stmt in _UPGRADE_STATEMENTS:
        op.execute(sa.text(stmt))


def downgrade() -> None:
    for stmt in _DOWNGRADE_STATEMENTS:
        op.execute(sa.text(stmt))
