from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from app.models.events.secure_event import SecureEvent
from app.models.events.face_registration import FaceRegistration
from app.models.events.audit_log import EventAuditLog
from app.models.events.totem import Totem
from engines.base_engine import get_engine
from app.services.events.webhook_service import send_webhook_async
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


async def register_face(
    event: SecureEvent,
    ticket_id: str,
    image_base64: str,
    db: Session
) -> dict:
    engine = get_engine()
    
    try:
        external_face_id = await engine.index_face(
            namespace=event.namespace,
            image_base64=image_base64,
            ticket_id=ticket_id
        )
    except ValueError as e:
        logger.warning(f"Face registration failed for {ticket_id}: {e}")
        send_webhook_async("fraud.photo_attempt", {
            "event_id": str(event.id),
            "ticket_id": ticket_id,
            "issues": [str(e)],
            "timestamp": datetime.utcnow().isoformat()
        })
        return {"success": False, "issues": [str(e)]}
    
    registration = FaceRegistration(
        event_id=event.id,
        ticket_id=ticket_id,
        external_face_id=external_face_id,
        status="active"
    )
    db.add(registration)
    
    log = EventAuditLog(
        action="face.registered",
        event_id=event.id,
        ticket_id=ticket_id,
        actor_type="api"
    )
    db.add(log)
    db.commit()
    
    send_webhook_async("face.registered", {
        "event_id": str(event.id),
        "ticket_id": ticket_id,
        "person_id": str(registration.id),
        "timestamp": datetime.utcnow().isoformat()
    })
    
    return {"success": True, "face_registration_id": registration.id}


async def delete_face(
    event: SecureEvent,
    ticket_id: str,
    reason: str,
    db: Session
) -> dict:
    engine = get_engine()
    
    reg = db.query(FaceRegistration).filter_by(
        ticket_id=ticket_id,
        event_id=event.id
    ).first()
    
    if not reg:
        return {"success": False, "error": "Face not found"}
    
    if reg.external_face_id:
        try:
            await engine.delete_face(event.namespace, reg.external_face_id)
        except Exception as e:
            logger.error(f"Error deleting face from engine: {e}")
    
    reg.status = "deleted"
    reg.deleted_at = datetime.utcnow()
    
    log = EventAuditLog(
        action="face.deleted",
        event_id=event.id,
        ticket_id=ticket_id,
        actor_type="api",
        extra={"reason": reason}
    )
    db.add(log)
    db.commit()
    
    send_webhook_async("face.deleted", {
        "ticket_id": ticket_id,
        "event_id": event.id,
        "reason": reason
    })
    
    return {"success": True}


async def validate_face_registration(
    event: SecureEvent,
    image_base64: str,
    db: Session
) -> dict:
    engine = get_engine()
    
    quality_result = await engine.check_image_quality(image_base64)
    
    if not quality_result.has_face:
        return {
            "valid": False,
            "issues": ["No face detected in image"]
        }
    
    if quality_result.quality_score < settings.FACE_MIN_QUALITY_SCORE:
        return {
            "valid": False,
            "quality_score": quality_result.quality_score,
            "issues": quality_result.issues
        }
    
    return {
        "valid": True,
        "quality_score": quality_result.quality_score,
        "issues": []
    }


async def get_face_by_ticket(
    event: SecureEvent,
    ticket_id: str,
    db: Session
) -> Optional[FaceRegistration]:
    return db.query(FaceRegistration).filter_by(
        event_id=event.id,
        ticket_id=ticket_id
    ).first()


async def get_event_faces(
    event: SecureEvent,
    db: Session,
    status: str = None
) -> list:
    query = db.query(FaceRegistration).filter_by(event_id=event.id)
    
    if status:
        query = query.filter_by(status=status)
    
    return query.all()


async def count_event_faces(
    event: SecureEvent,
    db: Session,
    status: str = "active"
) -> int:
    return db.query(FaceRegistration).filter_by(
        event_id=event.id,
        status=status
    ).count()