from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.types import Enum as SqlaEnum
from .base import Base
from .enums import TrainStatusEnum


class Train(Base):
    __tablename__ = "trains"
    __table_args__ = (Index("idx_trains_number", "number"),)

    id = Column(Integer, primary_key=True, index=True)
    number = Column(String(20), nullable=False, unique=True, index=True)
    line_id = Column(Integer, ForeignKey("lines.id", ondelete="SET NULL"), nullable=True)
    status = Column(SqlaEnum(TrainStatusEnum, name="train_status_enum"), nullable=False, default=TrainStatusEnum.on_time)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    line = relationship("Line", back_populates="trains")
    nearest_alerts = relationship("Alert", back_populates="nearest_train")
    affected_alerts = relationship("AlertAffectedTrain", back_populates="train", cascade="all, delete")
