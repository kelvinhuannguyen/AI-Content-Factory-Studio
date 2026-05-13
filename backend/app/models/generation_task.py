import uuid
from enum import Enum as PyEnum
from datetime import datetime
from sqlalchemy import String, Integer, Text, Enum, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from .base import UUIDBase


class TaskType(str, PyEnum):
    character_image = "character_image"
    video_clip = "video_clip"
    voiceover = "voiceover"
    sound_effect = "sound_effect"
    assembly = "assembly"
    quality_score = "quality_score"
    seo = "seo"
    thumbnail = "thumbnail"


class TaskStatus(str, PyEnum):
    queued = "queued"
    running = "running"
    success = "success"
    failed = "failed"
    retrying = "retrying"
    cancelled = "cancelled"


class GenerationTask(UUIDBase):
    __tablename__ = "generation_tasks"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scene_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    task_type: Mapped[TaskType] = mapped_column(Enum(TaskType), nullable=False)
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus), nullable=False, default=TaskStatus.queued
    )
    progress_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_r2_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
