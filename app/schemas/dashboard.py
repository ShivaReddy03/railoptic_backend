from pydantic import BaseModel
from typing import Optional


class DashboardCriticalAlert(BaseModel):
    id: str
    objectCategory: str
    line: str
    node: str
    date: str
    time: str
    severity: str
    status: str
    confidence: int
    riskScore: int
    nearestTrain: Optional[str] = None
    distanceKm: Optional[float] = None
    etaSec: Optional[int] = None
    imageUrl: Optional[str] = None

    class Config:
        alias_generator = lambda string: string
        allow_population_by_field_name = True


class AffectedTrainOut(BaseModel):
    id: str
    number: str
    distanceFromIncidentKm: float
    etaMin: int
    status: str

    class Config:
        alias_generator = lambda string: string
        allow_population_by_field_name = True


class DashboardOverviewResponse(BaseModel):
    activeAlerts: int
    criticalCount: int
    warningCount: int
    totalNodes: int
    onlineNodes: int
    activeTrains: int
    systemHealth: int
    critical: Optional[DashboardCriticalAlert]
    affectedTrains: list[AffectedTrainOut]

    class Config:
        alias_generator = lambda string: string
        allow_population_by_field_name = True
