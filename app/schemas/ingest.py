from pydantic import BaseModel
from typing import Optional


class IngestResponse(BaseModel):
    alert_id: Optional[str]
    risk_score: int
    hazard_count: int
    object_category: Optional[str]
    image_url: str

    class Config:
        alias_generator = lambda string: string
        validate_by_name = True
