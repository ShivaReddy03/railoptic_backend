from sqlalchemy import Column, String, Integer, ForeignKey, Float, DateTime, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.types import Enum as SqlaEnum
from .base import Base
from .enums import NodeStatusEnum


class Node(Base):
    __tablename__ = "nodes"
    __table_args__ = (Index("idx_nodes_status", "status"),)

    id = Column(String(10), primary_key=True)
    line_id = Column(Integer, ForeignKey("lines.id", ondelete="CASCADE"), nullable=False, index=True)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    status = Column(SqlaEnum(NodeStatusEnum, name="node_status_enum"), nullable=False, default=NodeStatusEnum.normal)
    health = Column(Integer, nullable=False, default=100)
    last_seen = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    line = relationship("Line", back_populates="nodes")
    alerts = relationship("Alert", back_populates="node", cascade="all, delete")
