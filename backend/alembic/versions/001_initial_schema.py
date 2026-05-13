"""initial schema — 8 tables (pure SQL, fully idempotent)

Revision ID: 001
Revises:
Create Date: 2026-05-13
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

# Mỗi statement riêng biệt — asyncpg không cho phép multi-statement trong 1 execute
_UPGRADE_STATEMENTS = [
    # ENUMs — idempotent (bỏ qua nếu đã tồn tại)
    "DO $$ BEGIN CREATE TYPE productiontype AS ENUM ('short_video', 'long_video', 'music_mv'); EXCEPTION WHEN duplicate_object THEN null; END $$",
    "DO $$ BEGIN CREATE TYPE projectstatus AS ENUM ('draft', 'topic_selected', 'script_ready', 'config_done', 'character_selected', 'scenes_ready', 'generating', 'assembly', 'quality_review', 'human_review', 'seo_ready', 'seo_approved', 'publishing', 'published', 'failed'); EXCEPTION WHEN duplicate_object THEN null; END $$",
    "DO $$ BEGIN CREATE TYPE scenestatus AS ENUM ('pending', 'generating', 'ready', 'failed'); EXCEPTION WHEN duplicate_object THEN null; END $$",
    "DO $$ BEGIN CREATE TYPE charactersource AS ENUM ('ai_generated', 'user_upload'); EXCEPTION WHEN duplicate_object THEN null; END $$",
    "DO $$ BEGIN CREATE TYPE tasktype AS ENUM ('character_image', 'video_clip', 'voiceover', 'sound_effect', 'assembly', 'quality_score', 'seo', 'thumbnail'); EXCEPTION WHEN duplicate_object THEN null; END $$",
    "DO $$ BEGIN CREATE TYPE taskstatus AS ENUM ('queued', 'running', 'success', 'failed', 'retrying', 'cancelled'); EXCEPTION WHEN duplicate_object THEN null; END $$",

    # Tables — CREATE TABLE IF NOT EXISTS
    """CREATE TABLE IF NOT EXISTS projects (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        title VARCHAR(500) NOT NULL DEFAULT 'Dự án mới',
        production_type productiontype NOT NULL,
        status projectstatus NOT NULL DEFAULT 'draft',
        duration_seconds INTEGER,
        genre VARCHAR(100),
        style VARCHAR(100),
        topic TEXT,
        preferred_language VARCHAR(10) NOT NULL DEFAULT 'vi',
        final_video_r2_key VARCHAR(1000),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",

    """CREATE TABLE IF NOT EXISTS scripts (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        version INTEGER NOT NULL DEFAULT 1,
        content_raw TEXT,
        content_html TEXT,
        word_count INTEGER NOT NULL DEFAULT 0,
        estimated_duration_seconds INTEGER,
        approved BOOLEAN NOT NULL DEFAULT false,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",

    """CREATE TABLE IF NOT EXISTS scenes (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        scene_number INTEGER NOT NULL,
        title VARCHAR(300),
        description TEXT,
        video_prompt TEXT,
        duration_seconds INTEGER,
        status scenestatus NOT NULL DEFAULT 'pending',
        clip_r2_key VARCHAR(1000),
        thumbnail_r2_key VARCHAR(1000),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",

    """CREATE TABLE IF NOT EXISTS characters (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        name VARCHAR(200),
        description TEXT,
        variant_index INTEGER NOT NULL DEFAULT 0,
        image_r2_key VARCHAR(1000),
        is_selected BOOLEAN NOT NULL DEFAULT false,
        comfyui_workflow JSONB,
        source charactersource NOT NULL DEFAULT 'ai_generated',
        user_ref_r2_key VARCHAR(1000),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",

    """CREATE TABLE IF NOT EXISTS generation_tasks (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        scene_id UUID REFERENCES scenes(id) ON DELETE SET NULL,
        task_type tasktype NOT NULL,
        celery_task_id VARCHAR(255),
        status taskstatus NOT NULL DEFAULT 'queued',
        progress_pct INTEGER NOT NULL DEFAULT 0,
        result_r2_key VARCHAR(1000),
        error_message TEXT,
        attempts INTEGER NOT NULL DEFAULT 0,
        started_at TIMESTAMPTZ,
        completed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",

    """CREATE TABLE IF NOT EXISTS music_tracks (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        suno_song_id VARCHAR(200),
        title VARCHAR(300),
        genre VARCHAR(100),
        mood VARCHAR(100),
        bpm INTEGER,
        lyrics_concept TEXT,
        audio_r2_key VARCHAR(1000),
        duration_seconds INTEGER,
        is_selected BOOLEAN NOT NULL DEFAULT false,
        variant_index INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",

    """CREATE TABLE IF NOT EXISTS quality_scores (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        overall_score INTEGER NOT NULL DEFAULT 0,
        hook_strength INTEGER NOT NULL DEFAULT 0,
        story_coherence INTEGER NOT NULL DEFAULT 0,
        visual_quality INTEGER NOT NULL DEFAULT 0,
        audio_sync INTEGER NOT NULL DEFAULT 0,
        character_consistency INTEGER NOT NULL DEFAULT 0,
        pacing INTEGER NOT NULL DEFAULT 0,
        engagement_potential INTEGER NOT NULL DEFAULT 0,
        gpt_feedback TEXT,
        human_approved BOOLEAN,
        rejection_notes TEXT,
        scored_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",

    """CREATE TABLE IF NOT EXISTS seo_packages (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        title_variants JSONB,
        description TEXT,
        tags JSONB,
        thumbnail_r2_key VARCHAR(1000),
        thumbnail_prompt TEXT,
        youtube_video_id VARCHAR(50),
        published_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",

    # Indexes
    "CREATE INDEX IF NOT EXISTS ix_scripts_project_id ON scripts(project_id)",
    "CREATE INDEX IF NOT EXISTS ix_scenes_project_id ON scenes(project_id)",
    "CREATE INDEX IF NOT EXISTS ix_characters_project_id ON characters(project_id)",
    "CREATE INDEX IF NOT EXISTS ix_generation_tasks_project_id ON generation_tasks(project_id)",
    "CREATE INDEX IF NOT EXISTS ix_generation_tasks_scene_id ON generation_tasks(scene_id)",
    "CREATE INDEX IF NOT EXISTS ix_music_tracks_project_id ON music_tracks(project_id)",
    "CREATE INDEX IF NOT EXISTS ix_quality_scores_project_id ON quality_scores(project_id)",
    "CREATE INDEX IF NOT EXISTS ix_seo_packages_project_id ON seo_packages(project_id)",
]


def upgrade() -> None:
    for sql in _UPGRADE_STATEMENTS:
        op.execute(sa.text(sql))


def downgrade() -> None:
    for sql in [
        "DROP TABLE IF EXISTS seo_packages CASCADE",
        "DROP TABLE IF EXISTS quality_scores CASCADE",
        "DROP TABLE IF EXISTS music_tracks CASCADE",
        "DROP TABLE IF EXISTS generation_tasks CASCADE",
        "DROP TABLE IF EXISTS characters CASCADE",
        "DROP TABLE IF EXISTS scenes CASCADE",
        "DROP TABLE IF EXISTS scripts CASCADE",
        "DROP TABLE IF EXISTS projects CASCADE",
        "DROP TYPE IF EXISTS productiontype",
        "DROP TYPE IF EXISTS projectstatus",
        "DROP TYPE IF EXISTS scenestatus",
        "DROP TYPE IF EXISTS charactersource",
        "DROP TYPE IF EXISTS tasktype",
        "DROP TYPE IF EXISTS taskstatus",
    ]:
        op.execute(sa.text(sql))
