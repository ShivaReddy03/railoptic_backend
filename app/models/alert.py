from sqlalchemy import Column, String, Integer, ForeignKey, Text, Numeric, DateTime, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.types import Enum as SqlaEnum
from .base import Base
from .enums import SeverityEnum, AlertStatusEnum


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("idx_alerts_status", "status"),
        Index("idx_alerts_severity", "severity"),
        Index("idx_alerts_node_id", "node_id"),
        Index("idx_alerts_detected", "detected_at"),
    )

    id = Column(String(20), primary_key=True)
    node_id = Column(String(10), ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    object_category = Column(String(100), nullable=False)
    title = Column(String(200), nullable=False)
    source = Column(String(50), nullable=False, default="AI Camera")
    severity = Column(SqlaEnum(SeverityEnum, name="severity_enum"), nullable=False)
    status = Column(SqlaEnum(AlertStatusEnum, name="alert_status_enum"), nullable=False, default=AlertStatusEnum.active)
    confidence = Column(Integer, nullable=False)
    risk_score = Column(Integer, nullable=False)
    nearest_train_id = Column(Integer, ForeignKey("trains.id", ondelete="SET NULL"), nullable=True)
    distance_km = Column(Numeric(6, 2), nullable=True)
    eta_sec = Column(Integer, nullable=True)
    image_url = Column(Text, nullable=True)
    detected_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by = Column(Integer, nullable=True)
    escalated_to = Column(String(20), nullable=True)
    escalated_at = Column(DateTime(timezone=True), nullable=True)
    escalated_by = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)

    node = relationship("Node", back_populates="alerts")
    nearest_train = relationship("Train", back_populates="nearest_alerts")
    affected_trains = relationship("AlertAffectedTrain", back_populates="alert", cascade="all, delete")
