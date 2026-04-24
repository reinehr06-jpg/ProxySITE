from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from app.models.events.secure_event import SecureEvent
from app.models.events.totem import Totem
from app.models.events.qr_validation import QRValidation
from app.models.events.face_registration import FaceRegistration
from app.models.events.audit_log import EventAuditLog
from app.services.events.webhook_service import send_webhook_async
import logging
import uuid

logger = logging.getLogger(__name__)


async def validate_qr_code(
    event: SecureEvent,
    qr_token: str,
    totem: Totem = None,
    operator_id: str = None,
    device_fingerprint: str = None,
    ip_address: str = None,
    geolocation: dict = None,
    db: Session = None
) -> dict:
    import json
    import base64
    
    try:
        qr_data = json.loads(base64.b64decode(qr_token).decode())
    except Exception as e:
        logger.warning(f"Invalid QR token: {e}")
        
        validation = QRValidation(
            event_id=event.id,
            ticket_id=qr_token[:50] if qr_token else "unknown",
            totem_id=totem.id if totem else None,
            operator_id=operator_id,
            result="invalid",
            device_fingerprint=device_fingerprint,
            ip_address=ip_address,
            geolocation=geolocation
        )
        db.add(validation)
        db.commit()
        
        send_webhook_async("checkin.invalid", {
            "event_id": str(event.id),
            "ticket_id": ticket_id,
            "totem_id": str(totem.id) if totem else None,
            "reason": "Invalid token format",
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return {
            "valid": False,
            "result": "invalid",
            "message": "Invalid QR code format"
        }
    
    ticket_id = qr_data.get("ticket_id")
    event_id = qr_data.get("event_id")
    
    if not ticket_id:
        return {
            "valid": False,
            "result": "invalid",
            "message": "Missing ticket_id in QR"
        }
    
    if str(event_id) != str(event.id):
        return {
            "valid": False,
            "result": "invalid",
            "message": "QR code is for a different event"
        }
    
    existing = db.query(QRValidation).filter_by(
        event_id=event.id,
        ticket_id=ticket_id,
        result="valid"
    ).first()
    
    if existing:
        send_webhook_async("checkin.already_used", {
            "event_id": str(event.id),
            "ticket_id": ticket_id,
            "totem_id": str(totem.id) if totem else None,
            "first_use_at": existing.validated_at.isoformat() if existing.validated_at else None,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return {
            "valid": False,
            "result": "already_used",
            "ticket_id": ticket_id,
            "first_use_at": existing.validated_at.isoformat() if existing.validated_at else None
        }
    
    validation = QRValidation(
        event_id=event.id,
        ticket_id=ticket_id,
        totem_id=totem.id if totem else None,
        operator_id=operator_id,
        result="valid",
        device_fingerprint=device_fingerprint,
        ip_address=ip_address,
        geolocation=geolocation
    )
    db.add(validation)
    
    log = EventAuditLog(
        action="qr.validated",
        event_id=event.id,
        ticket_id=ticket_id,
        totem_id=str(totem.id) if totem else None,
        actor_type="totem" if totem else "api",
        actor_id=operator_id,
        ip_address=ip_address
    )
    db.add(log)
    db.commit()
    
    send_webhook_async("checkin.validated", {
        "event_id": str(event.id),
        "ticket_id": ticket_id,
        "totem_id": str(totem.id) if totem else None,
        "zone": totem.zone if totem else None,
        "method": "qr",
        "operator_code": operator_id,
        "timestamp": datetime.utcnow().isoformat()
    })
    
    return {
        "valid": True,
        "result": "valid",
        "ticket_id": ticket_id
    }


async def get_offline_qr_validations(
    event: SecureEvent,
    db: Session
) -> list:
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(hours=24)
    
    return db.query(QRValidation).filter(
        QRValidation.event_id == event.id,
        QRValidation.validated_at > cutoff
    ).all()


async def sync_offline_validations(
    event: SecureEvent,
    validations: list,
    db: Session
) -> dict:
    synced = 0
    duplicates = 0
    
    for val in validations:
        existing = db.query(QRValidation).filter_by(
            event_id=event.id,
            ticket_id=val.get("ticket_id"),
            result="valid"
        ).first()
        
        if existing:
            duplicates += 1
            continue
        
        validation = QRValidation(
            event_id=event.id,
            ticket_id=val.get("ticket_id"),
            totem_id=val.get("totem_id"),
            result="valid",
            device_fingerprint=val.get("device_fingerprint"),
            ip_address=val.get("ip_address")
        )
        db.add(validation)
        synced += 1
    
    db.commit()
    
    return {
        "synced": synced,
        "duplicates": duplicates
    }


async def get_qr_stats(
    event: SecureEvent,
    db: Session
) -> dict:
    total = db.query(QRValidation).filter_by(
        event_id=event.id,
        result="valid"
    ).count()
    
    invalid = db.query(QRValidation).filter_by(
        event_id=event.id,
        result="invalid"
    ).count()
    
    already_used = db.query(QRValidation).filter_by(
        event_id=event.id,
        result="already_used"
    ).count()
    
    return {
        "total_valid": total,
        "invalid": invalid,
        "already_used": already_used
    }