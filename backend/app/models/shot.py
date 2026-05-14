import uuid
from sqlalchemy import String, Integer, Text, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from .base import UUIDBase


class Shot(UUIDBase):
    __tablename__ = "shots"

    scene_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shot_id: Mapped[str] = mapped_column(String(50), nullable=False)      # "SC01_SH01"
    shot_number: Mapped[int] = mapped_column(Integer, nullable=False)
    duration: Mapped[int] = mapped_column(Integer, nullable=False)         # seconds ≤ 8
    prompt: Mapped[str] = mapped_column(Text, nullable=False)              # Production Formula prompt
    characters_present: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    qc_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    qc_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="APPROVED")
    clip_r2_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # ── Continuity Director fields (Migration 006) ────────────────────────
    continuity_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    sfx_prompt:       Mapped[str | None] = mapped_column(Text, nullable=True)
    ambience:         Mapped[str | None] = mapped_column(String(500), nullable=True)
    motion_intensity: Mapped[int | None] = mapped_column(Integer, nullable=True)
