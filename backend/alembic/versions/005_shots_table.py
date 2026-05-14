"""Shots table — Cinematic Scene Decomposer output

Revision ID: 005
Revises: 004
Create Date: 2026-05-14
"""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None

_UPGRADE_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS shots (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        scene_id UUID NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        shot_id VARCHAR(50) NOT NULL,
        shot_number INTEGER NOT NULL,
        duration INTEGER NOT NULL,
        prompt TEXT NOT NULL,
        characters_present JSONB,
        qc_score REAL,
        qc_notes TEXT,
        status VARCHAR(20) NOT NULL DEFAULT 'APPROVED',
        clip_r2_key VARCHAR(1000),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_shots_project_id ON shots(project_id)",
    "CREATE INDEX IF NOT EXISTS ix_shots_scene_id ON shots(scene_id)",
]

_DOWNGRADE_STATEMENTS = [
    "DROP TABLE IF EXISTS shots CASCADE",
]


def upgrade() -> None:
    for stmt in _UPGRADE_STATEMENTS:
        op.execute(sa.text(stmt))


def downgrade() -> None:
    for stmt in _DOWNGRADE_STATEMENTS:
        op.execute(sa.text(stmt))
