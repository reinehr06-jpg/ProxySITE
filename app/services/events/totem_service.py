import secrets
import hashlib
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from app.models.events.secure_event import SecureEvent
from app.models.events.totem import Totem
from app.models.events.audit_log import EventAuditLog
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


def generate_totem_api_key() -> str:
    salt = settings.TOTEM_API_KEY_SALT
    raw_key = secrets.token_hex(32)
    key_hash = hashlib.sha256(f"{raw_key}{salt}".encode()).hexdigest()
    return f"totem_{raw_key}"


async def create_totem(
    event: SecureEvent,
    name: str,
    zone: str,
    mode: str = "both",
    db: Session = None
) -> Totem:
    api_key = generate_totem_api_key()
    
    totem = Totem(
        event_id=event.id,
        name=name,
        zone=zone,
        mode=mode,
        api_key=api_key,
        status="active"
    )
    
    db.add(totem)
    
    log = EventAuditLog(
        action="totem.created",
        event_id=event.id,
        totem_id=str(totem.id),
        actor_type="admin"
    )
    db.add(log)
    db.commit()
    
    return totem


async def get_totem(
    totem_id: str,
    db: Session
) -> Optional[Totem]:
    return db.query(Totem).filter_by(id=totem_id).first()


async def get_event_totems(
    event: SecureEvent,
    db: Session,
    status: str = None
) -> list:
    query = db.query(Totem).filter_by(event_id=event.id)
    
    if status:
        query = query.filter_by(status=status)
    
    return query.all()


async def update_totem(
    totem_id: str,
    data: dict,
    db: Session
) -> Optional[Totem]:
    totem = db.query(Totem).filter_by(id=totem_id).first()
    
    if not totem:
        return None
    
    if "name" in data:
        totem.name = data["name"]
    if "zone" in data:
        totem.zone = data["zone"]
    if "mode" in data:
        totem.mode = data["mode"]
    if "status" in data:
        totem.status = data["status"]
    
    db.commit()
    db.refresh(totem)
    
    return totem


async def delete_totem(
    totem_id: str,
    db: Session
) -> bool:
    totem = db.query(Totem).filter_by(id=totem_id).first()
    
    if not totem:
        return False
    
    event_id = totem.event_id
    
    db.delete(totem)
    
    log = EventAuditLog(
        action="totem.deleted",
        event_id=event_id,
        totem_id=totem_id,
        actor_type="admin"
    )
    db.add(log)
    db.commit()
    
    return True


async def regenerate_totem_key(
    totem_id: str,
    db: Session
) -> Optional[dict]:
    totem = db.query(Totem).filter_by(id=totem_id).first()
    
    if not totem:
        return None
    
    old_key = totem.api_key
    new_key = generate_totem_api_key()
    totem.api_key = new_key
    
    log = EventAuditLog(
        action="totem.key_regenerated",
        event_id=totem.event_id,
        totem_id=totem_id,
        actor_type="admin",
        extra={"old_key_prefix": old_key[:20]}
    )
    db.add(log)
    db.commit()
    
    return {
        "totem_id": totem_id,
        "new_api_key": new_key
    }


async def heartbeat_totem(
    totem_id: str,
    db: Session
) -> Optional[Totem]:
    totem = db.query(Totem).filter_by(id=totem_id).first()
    
    if not totem:
        return None
    
    totem.last_seen_at = datetime.utcnow()
    totem.status = "active"
    db.commit()
    
    return totem


async def get_totem_status(
    event: SecureEvent,
    db: Session
) -> dict:
    from datetime import timedelta
    
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=5)
    
    totems = db.query(Totem).filter_by(event_id=event.id).all()
    
    online = 0
    offline = 0
    
    for totem in totems:
        if totem.last_seen_at and totem.last_seen_at > cutoff:
            online += 1
        else:
            offline += 1
    
    return {
        "total": len(totems),
        "online": online,
        "offline": offline
    }


async def revoke_totem(
    totem_id: str,
    db: Session
) -> bool:
    totem = db.query(Totem).filter_by(id=totem_id).first()
    
    if not totem:
        return False
    
    totem.status = "revoked"
    
    log = EventAuditLog(
        action="totem.revoked",
        event_id=totem.event_id,
        totem_id=totem_id,
        actor_type="admin"
    )
    db.add(log)
    db.commit()
    
    return True