"""approval_tokens table + projects subtitle/bgm columns

Revision ID: 002
Revises: 001
Create Date: 2026-05-14
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

_UPGRADE_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS approval_tokens (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        step VARCHAR(100) NOT NULL,
        action_hint VARCHAR(50),
        token VARCHAR(100) NOT NULL UNIQUE,
        consumed BOOLEAN NOT NULL DEFAULT false,
        expires_at TIMESTAMPTZ NOT NULL,
        consumed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_approval_tokens_project_id ON approval_tokens(project_id)",
    "CREATE INDEX IF NOT EXISTS ix_approval_tokens_token ON approval_tokens(token)",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS subtitle_r2_key VARCHAR(1000)",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS bgm_r2_key VARCHAR(1000)",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS video_retry_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS script_retry_count INTEGER NOT NULL DEFAULT 0",
]

_DOWNGRADE_STATEMENTS = [
    "DROP TABLE IF EXISTS approval_tokens CASCADE",
    "ALTER TABLE projects DROP COLUMN IF EXISTS subtitle_r2_key",
    "ALTER TABLE projects DROP COLUMN IF EXISTS bgm_r2_key",
    "ALTER TABLE projects DROP COLUMN IF EXISTS video_retry_count",
    "ALTER TABLE projects DROP COLUMN IF EXISTS script_retry_count",
]


def upgrade() -> None:
    for stmt in _UPGRADE_STATEMENTS:
        op.execute(sa.text(stmt))


def downgrade() -> None:
    for stmt in _DOWNGRADE_STATEMENTS:
        op.execute(sa.text(stmt))
