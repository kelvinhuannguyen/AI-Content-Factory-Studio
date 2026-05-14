import uuid
from enum import Enum as PyEnum
from sqlalchemy import String, Integer, Text, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from .base import UUIDBase


class SceneStatus(str, PyEnum):
    pending = "pending"
    generating = "generating"
    ready = "ready"
    failed = "failed"


class Scene(UUIDBase):
    __tablename__ = "scenes"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scene_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[SceneStatus] = mapped_column(
        Enum(SceneStatus), nullable=False, default=SceneStatus.pending
    )
    clip_r2_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    thumbnail_r2_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    characters_in_scene: Mapped[list | None] = mapped_column(JSONB, nullable=True)
