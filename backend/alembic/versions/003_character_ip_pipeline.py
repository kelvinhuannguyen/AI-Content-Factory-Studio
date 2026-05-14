"""Character IP Pipeline — add ref_id, VIS, DNA, palette, sheet to characters; characters_in_scene to scenes

Revision ID: 003
Revises: 002
Create Date: 2026-05-14
"""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None

_UPGRADE_STATEMENTS = [
    # characters table — IP character fields
    "ALTER TABLE characters ADD COLUMN IF NOT EXISTS character_index INTEGER DEFAULT 0",
    "ALTER TABLE characters ADD COLUMN IF NOT EXISTS ref_id VARCHAR(20)",
    "ALTER TABLE characters ADD COLUMN IF NOT EXISTS visual_identity_string TEXT",
    "ALTER TABLE characters ADD COLUMN IF NOT EXISTS character_role VARCHAR(20)",
    "ALTER TABLE characters ADD COLUMN IF NOT EXISTS physical_dna JSONB",
    "ALTER TABLE characters ADD COLUMN IF NOT EXISTS color_palette JSONB",
    "ALTER TABLE characters ADD COLUMN IF NOT EXISTS sheet_r2_key VARCHAR(500)",
    "ALTER TABLE characters ADD COLUMN IF NOT EXISTS user_prompt_addition TEXT",
    "CREATE INDEX IF NOT EXISTS ix_characters_ref_id ON characters(ref_id)",
    "CREATE INDEX IF NOT EXISTS ix_characters_char_index ON characters(project_id, character_index)",
    # scenes table — regional prompting support
    "ALTER TABLE scenes ADD COLUMN IF NOT EXISTS characters_in_scene JSONB",
]

_DOWNGRADE_STATEMENTS = [
    "ALTER TABLE characters DROP COLUMN IF EXISTS character_index",
    "ALTER TABLE characters DROP COLUMN IF EXISTS ref_id",
    "ALTER TABLE characters DROP COLUMN IF EXISTS visual_identity_string",
    "ALTER TABLE characters DROP COLUMN IF EXISTS character_role",
    "ALTER TABLE characters DROP COLUMN IF EXISTS physical_dna",
    "ALTER TABLE characters DROP COLUMN IF EXISTS color_palette",
    "ALTER TABLE characters DROP COLUMN IF EXISTS sheet_r2_key",
    "ALTER TABLE characters DROP COLUMN IF EXISTS user_prompt_addition",
    "ALTER TABLE scenes DROP COLUMN IF EXISTS characters_in_scene",
]


def upgrade() -> None:
    for stmt in _UPGRADE_STATEMENTS:
        op.execute(sa.text(stmt))


def downgrade() -> None:
    for stmt in _DOWNGRADE_STATEMENTS:
        op.execute(sa.text(stmt))
