from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from app.models.events.secure_event import SecureEvent
from app.models.events.totem import Totem
from app.models.events.checkin_attempt import CheckinAttempt
from app.models.events.face_registration import FaceRegistration
from app.models.events.audit_log import EventAuditLog
from engines.base_engine import get_engine
from app.services.events.webhook_service import send_webhook_async
import logging

logger = logging.getLogger(__name__)


async def recognize_face(
    event: SecureEvent,
    totem: Totem,
    image_base64: str,
    db: Session
) -> dict:
    engine = get_engine()
    
    match = await engine.search_face(
        namespace=event.namespace,
        image_base64=image_base64
    )
    
    if not match:
        attempt = CheckinAttempt(
            event_id=event.id,
            totem_id=totem.id,
            matched=False,
            result="not_found"
        )
        db.add(attempt)
        db.commit()
        
        send_webhook_async("fraud.not_found", {
            "event_id": str(event.id),
            "totem_id": str(totem.id),
            "attempt_id": str(attempt.id),
            "timestamp": datetime.utcnow().isoformat()
        })
        
        log = EventAuditLog(
            action="checkin.attempt",
            event_id=event.id,
            totem_id=str(totem.id),
            actor_type="totem",
            extra={"result": "not_found"}
        )
        db.add(log)
        db.commit()
        
        return {
            "matched": False,
            "result": "not_found"
        }
    
    already_in = db.query(CheckinAttempt).filter_by(
        ticket_id=match.ticket_id,
        event_id=event.id,
        matched=True
    ).first()
    
    if already_in:
        attempt = CheckinAttempt(
            event_id=event.id,
            totem_id=totem.id,
            ticket_id=match.ticket_id,
            matched=True,
            confidence_score=match.confidence,
            result="already_checked_in"
        )
        db.add(attempt)
        db.commit()
        
        send_webhook_async("checkin.already_used", {
            "event_id": str(event.id),
            "ticket_id": match.ticket_id,
            "totem_id": str(totem.id),
            "first_checkin_at": already_in.attempted_at.isoformat() if already_in.attempted_at else None,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        log = EventAuditLog(
            action="checkin.attempt",
            event_id=event.id,
            ticket_id=match.ticket_id,
            totem_id=str(totem.id),
            actor_type="totem",
            extra={"result": "already_checked_in", "confidence": match.confidence}
        )
        db.add(log)
        db.commit()
        
        return {
            "matched": True,
            "result": "already_checked_in",
            "ticket_id": match.ticket_id,
            "first_checkin_at": already_in.attempted_at.isoformat() if already_in.attempted_at else None
        }
    
    attempt = CheckinAttempt(
        event_id=event.id,
        totem_id=totem.id,
        ticket_id=match.ticket_id,
        matched=True,
        confidence_score=match.confidence,
        result="identified"
    )
    db.add(attempt)
    
    face_reg = db.query(FaceRegistration).filter_by(
        event_id=event.id,
        ticket_id=match.ticket_id
    ).first()
    if face_reg:
        attempt.face_registration_id = face_reg.id
    
    log = EventAuditLog(
        action="checkin.identified",
        event_id=event.id,
        ticket_id=match.ticket_id,
        totem_id=str(totem.id),
        actor_type="totem",
        extra={"confidence": match.confidence, "zone": totem.zone}
    )
    db.add(log)
    db.commit()
    
    send_webhook_async("face.identified", {
        "event_id": str(event.id),
        "ticket_id": match.ticket_id,
        "totem_id": str(totem.id),
        "confidence": match.confidence,
        "zone": totem.zone,
        "method": "face",
        "timestamp": datetime.utcnow().isoformat()
    })
    
    return {
        "matched": True,
        "result": "identified",
        "ticket_id": match.ticket_id,
        "confidence": match.confidence,
        "zone": totem.zone
    }


async def get_event_checkins(
    event: SecureEvent,
    db: Session,
    limit: int = 100,
    offset: int = 0
) -> list:
    return db.query(CheckinAttempt).filter_by(
        event_id=event.id
    ).order_by(CheckinAttempt.attempted_at.desc()).offset(offset).limit(limit).all()


async def get_checkin_stats(
    event: SecureEvent,
    db: Session
) -> dict:
    from sqlalchemy import func
    
    total = db.query(CheckinAttempt).filter_by(
        event_id=event.id,
        matched=True,
        result="identified"
    ).count()
    
    unique = db.query(
        CheckinAttempt.ticket_id,
        func.count(CheckinAttempt.id)
    ).filter(
        CheckinAttempt.event_id == event.id,
        CheckinAttempt.matched == True,
        CheckinAttempt.result == "identified"
    ).group_by(CheckinAttempt.ticket_id).count()
    
    not_found = db.query(CheckinAttempt).filter_by(
        event_id=event.id,
        result="not_found"
    ).count()
    
    already_in = db.query(CheckinAttempt).filter_by(
        event_id=event.id,
        result="already_checked_in"
    ).count()
    
    return {
        "total_checkins": total,
        "unique_people": unique,
        "not_found": not_found,
        "already_checked_in": already_in
    }


async def get_live_checkins(
    event: SecureEvent,
    db: Session,
    since: datetime = None
) -> list:
    query = db.query(CheckinAttempt).filter_by(
        event_id=event.id,
        matched=True
    ).order_by(CheckinAttempt.attempted_at.desc())
    
    if since:
        query = query.filter(CheckinAttempt.attempted_at > since)
    
    return query.limit(50).all()