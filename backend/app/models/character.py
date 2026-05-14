import uuid
from enum import Enum as PyEnum
from sqlalchemy import String, Integer, Text, Boolean, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from .base import UUIDBase


class CharacterSource(str, PyEnum):
    ai_generated = "ai_generated"
    user_upload = "user_upload"


class Character(UUIDBase):
    __tablename__ = "characters"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    variant_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    image_r2_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    is_selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    comfyui_workflow: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source: Mapped[CharacterSource] = mapped_column(
        Enum(CharacterSource), nullable=False, default=CharacterSource.ai_generated
    )
    user_ref_r2_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # IP Character Pipeline fields (migration 003)
    character_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ref_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    visual_identity_string: Mapped[str | None] = mapped_column(Text, nullable=True)
    character_role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    physical_dna: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    color_palette: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    sheet_r2_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    user_prompt_addition: Mapped[str | None] = mapped_column(Text, nullable=True)
