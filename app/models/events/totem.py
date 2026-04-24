from sqlalchemy import Column, String, DateTime, ForeignKey, func
from app.core.database import Base
import uuid


class Totem(Base):
    __tablename__ = "totems"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(String, ForeignKey("secure_events.id"), nullable=False)
    name = Column(String(100))
    zone = Column(String(100))
    mode = Column(String(20), default="both")
    api_key = Column(String(255), unique=True, nullable=False)
    last_seen_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=func.now())