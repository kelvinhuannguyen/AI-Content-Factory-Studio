"""Shots continuity fields — Sequence Continuity & Motion Coherence Director

Revision ID: 006
Revises: 005
Create Date: 2026-05-14
"""
from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None

_UPGRADE_STATEMENTS = [
    "ALTER TABLE shots ADD COLUMN IF NOT EXISTS continuity_notes TEXT",
    "ALTER TABLE shots ADD COLUMN IF NOT EXISTS sfx_prompt TEXT",
    "ALTER TABLE shots ADD COLUMN IF NOT EXISTS ambience VARCHAR(500)",
    "ALTER TABLE shots ADD COLUMN IF NOT EXISTS motion_intensity INTEGER",
]

_DOWNGRADE_STATEMENTS = [
    "ALTER TABLE shots DROP COLUMN IF EXISTS continuity_notes",
    "ALTER TABLE shots DROP COLUMN IF EXISTS sfx_prompt",
    "ALTER TABLE shots DROP COLUMN IF EXISTS ambience",
    "ALTER TABLE shots DROP COLUMN IF EXISTS motion_intensity",
]


def upgrade() -> None:
    for stmt in _UPGRADE_STATEMENTS:
        op.execute(sa.text(stmt))


def downgrade() -> None:
    for stmt in _DOWNGRADE_STATEMENTS:
        op.execute(sa.text(stmt))
