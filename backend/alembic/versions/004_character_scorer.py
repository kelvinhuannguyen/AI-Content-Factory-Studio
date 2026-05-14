"""Character Scorer — add ai_score, correction_brief columns to characters table

Revision ID: 004
Revises: 003
Create Date: 2026-05-14
"""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

_UPGRADE_STATEMENTS = [
    "ALTER TABLE characters ADD COLUMN IF NOT EXISTS ai_score INTEGER",
    "ALTER TABLE characters ADD COLUMN IF NOT EXISTS correction_brief TEXT",
]

_DOWNGRADE_STATEMENTS = [
    "ALTER TABLE characters DROP COLUMN IF EXISTS ai_score",
    "ALTER TABLE characters DROP COLUMN IF EXISTS correction_brief",
]


def upgrade() -> None:
    for stmt in _UPGRADE_STATEMENTS:
        op.execute(sa.text(stmt))


def downgrade() -> None:
    for stmt in _DOWNGRADE_STATEMENTS:
        op.execute(sa.text(stmt))
