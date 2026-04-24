from sqlalchemy import Column, String, DateTime, JSON, func
from app.core.database import Base
import uuid


class EventAuditLog(Base):
    __tablename__ = "event_audit_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    action = Column(String(100), nullable=False)
    event_id = Column(String, nullable=True)
    ticket_id = Column(String, nullable=True)
    totem_id = Column(String, nullable=True)
    actor_type = Column(String(20))
    actor_id = Column(String(255), nullable=True)
    ip_address = Column(String(45), nullable=True)
    extra = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=func.now())