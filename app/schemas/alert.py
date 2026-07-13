from pydantic import BaseModel
from typing import Optional


class AlertOut(BaseModel):
    id: str
    date: str
    time: str
    zone: str
    line: str
    node: str
    objectCategory: str
    title: str
    source: str
    location: str
    severity: str
    status: str
    confidence: int
    riskScore: int
    nearestTrain: Optional[str] = None
    distanceKm: Optional[float] = None
    etaSec: Optional[int] = None
    imageUrl: Optional[str] = None
    escalatedTo: Optional[str] = None
    escalatedAt: Optional[str] = None
    escalatedBy: Optional[int] = None

    class Config:
        alias_generator = lambda string: string
        validate_by_name = True


class AlertListResponse(BaseModel):
    data: list[AlertOut]
    total: int
    page: int
    pageSize: int

    class Config:
        alias_generator = lambda string: string
        validate_by_name = True
