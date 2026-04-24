from datetime import datetime
from sqlalchemy import Column, String, DateTime
from app.core.database import Base


class PairedSystem(Base):
    __tablename__ = "paired_systems"
    
    id = Column(String, primary_key=True)
    event_id = Column(String, nullable=False, index=True)
    system_name = Column(String, nullable=False)
    system_url = Column(String, nullable=False)
    status = Column(String, default="pending")
    pairing_token = Column(String)
    pairing_expires_at = Column(DateTime)
    public_key = Column(String)
    paired_at = Column(DateTime)
    revoked_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            "id": self.id,
            "event_id": self.event_id,
            "system_name": self.system_name,
            "system_url": self.system_url,
            "status": self.status,
            "paired_at": self.paired_at.isoformat() if self.paired_at else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None
        }