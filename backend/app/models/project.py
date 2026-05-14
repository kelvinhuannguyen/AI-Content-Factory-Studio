import uuid
from enum import Enum as PyEnum
from sqlalchemy import String, Integer, Text, Enum
from sqlalchemy.orm import Mapped, mapped_column
from .base import UUIDBase


class ProductionType(str, PyEnum):
    short_video = "short_video"
    long_video = "long_video"
    music_mv = "music_mv"


class ProjectStatus(str, PyEnum):
    draft = "draft"
    topic_selected = "topic_selected"
    script_ready = "script_ready"
    config_done = "config_done"
    character_selected = "character_selected"
    scenes_ready = "scenes_ready"
    generating = "generating"
    assembly = "assembly"
    quality_review = "quality_review"
    human_review = "human_review"
    seo_ready = "seo_ready"
    seo_approved = "seo_approved"
    publishing = "publishing"
    published = "published"
    failed = "failed"


class Project(UUIDBase):
    __tablename__ = "projects"

    title: Mapped[str] = mapped_column(String(500), nullable=False, default="Dự án mới")
    production_type: Mapped[ProductionType] = mapped_column(
        Enum(ProductionType), nullable=False
    )
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus), nullable=False, default=ProjectStatus.draft
    )
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    genre: Mapped[str | None] = mapped_column(String(100), nullable=True)
    style: Mapped[str | None] = mapped_column(String(100), nullable=True)
    topic: Mapped[str | None] = mapped_column(Text, nullable=True)
    preferred_language: Mapped[str] = mapped_column(String(10), nullable=False, default="vi")
    final_video_r2_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    blueprint_r2_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)
