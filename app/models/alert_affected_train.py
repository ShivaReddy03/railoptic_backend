from sqlalchemy import Column, Integer, ForeignKey, Numeric, String
from sqlalchemy.orm import relationship
from sqlalchemy.types import Enum as SqlaEnum
from .base import Base
from .enums import TrainStatusEnum


class AlertAffectedTrain(Base):
    __tablename__ = "alert_affected_trains"

    alert_id = Column(String(20), ForeignKey("alerts.id", ondelete="CASCADE"), primary_key=True)
    train_id = Column(Integer, ForeignKey("trains.id", ondelete="CASCADE"), primary_key=True)
    distance_from_incident = Column(Numeric(6, 2), nullable=False)
    eta_min = Column(Integer, nullable=False)
    status = Column(SqlaEnum(TrainStatusEnum, name="train_status_enum"), nullable=False)

    alert = relationship("Alert", back_populates="affected_trains")
    train = relationship("Train", back_populates="affected_alerts")
