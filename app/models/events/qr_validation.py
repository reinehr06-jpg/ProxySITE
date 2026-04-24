from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, func
from app.core.database import Base
import uuid


class QRValidation(Base):
    __tablename__ = "qr_validations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(String, ForeignKey("secure_events.id"))
    ticket_id = Column(String, nullable=False)
    totem_id = Column(String, nullable=True)
    operator_id = Column(String, nullable=True)
    result = Column(String(20))
    device_fingerprint = Column(String(255), nullable=True)
    ip_address = Column(String(45), nullable=True)
    geolocation = Column(JSON, nullable=True)
    validated_at = Column(DateTime, default=func.now())