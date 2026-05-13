import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Text, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from .base import UUIDBase


class QualityScore(UUIDBase):
    __tablename__ = "quality_scores"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    overall_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hook_strength: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    story_coherence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    visual_quality: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    audio_sync: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    character_consistency: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pacing: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    engagement_potential: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gpt_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_approved: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    rejection_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
