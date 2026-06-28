from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, UniqueConstraint, func
from sqlalchemy.orm import relationship
from .base import Base


class Line(Base):
    __tablename__ = "lines"
    __table_args__ = (UniqueConstraint("zone_id", "name", name="uq_line_zone_name"),)

    id = Column(Integer, primary_key=True, index=True)
    zone_id = Column(Integer, ForeignKey("zones.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    zone = relationship("Zone", back_populates="lines")
    nodes = relationship("Node", back_populates="line", cascade="all, delete")
    trains = relationship("Train", back_populates="line")
