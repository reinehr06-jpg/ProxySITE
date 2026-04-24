from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, func
from app.core.database import Base
import uuid


class FaceRegistration(Base):
    __tablename__ = "face_registrations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(String, ForeignKey("secure_events.id"), nullable=False)
    ticket_id = Column(String, unique=True, nullable=False)
    external_face_id = Column(String(255), nullable=True)
    storage_path = Column(String(500), nullable=True)
    status = Column(String(20), default="pending")
    captured_at = Column(DateTime, default=func.now())
    deleted_at = Column(DateTime, nullable=True)