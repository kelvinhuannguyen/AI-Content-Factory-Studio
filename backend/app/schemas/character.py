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

    model_config = {"from_attributes": True}
