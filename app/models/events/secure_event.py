from sqlalchemy import Column, String, Boolean, Integer, DateTime, func
from app.core.database import Base
import uuid


class SecureEvent(Base):
    __tablename__ = "secure_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    external_event_id = Column(String, unique=True, nullable=False)
    account_id = Column(String, nullable=False)
    name = Column(String(255), nullable=False)
    event_date = Column(DateTime, nullable=True)
    facial_enabled = Column(Boolean, default=True)
    namespace = Column(String(100), unique=True, nullable=False)
    status = Column(String(20), default="active")
    retention_days = Column(Integer, default=90)
    created_at = Column(DateTime, default=func.now())
    ended_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    
    rsa_private_key_encrypted = Column(String, nullable=True)
    totem_key_encrypted = Column(String, nullable=True)
    totem_key_hint = Column(String, nullable=True)