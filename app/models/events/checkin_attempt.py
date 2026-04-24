from sqlalchemy import Column, String, Boolean, Float, DateTime, ForeignKey, func
from app.core.database import Base
import uuid


class CheckinAttempt(Base):
    __tablename__ = "checkin_attempts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(String, ForeignKey("secure_events.id"))
    totem_id = Column(String, nullable=True)
    face_registration_id = Column(String, nullable=True)
    ticket_id = Column(String, nullable=True)
    matched = Column(Boolean, default=False)
    confidence_score = Column(Float, nullable=True)
    result = Column(String(30))
    image_path = Column(String(500), nullable=True)
    attempted_at = Column(DateTime, default=func.now())