from __future__ import annotations
import uuid
from pydantic import BaseModel
from ..models.character import CharacterSource


class CharacterGenerateRequest(BaseModel):
    project_id: uuid.UUID
    description: str
    name: str = ""


class CharacterOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str | None
    description: str | None
    variant_index: int
    image_r2_key: str | None
    image_url: str | None
    is_selected: bool
    source: CharacterSource
    user_ref_r2_key: str | None
    # IP Character Pipeline fields
    character_index: int = 0
    ref_id: str | None = None
    visual_identity_string: str | None = None
    character_role: str | None = None
    physical_dna: dict | None = None
    color_palette: dict | None = None
    sheet_r2_key: str | None = None
    sheet_url: str | None = None
    user_prompt_addition: str | None = None

    model_config = {"from_attributes": True}
