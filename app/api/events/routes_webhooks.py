from fastapi import APIRouter, Depends, HTTPException, Request, Header, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.core.database import get_db_secure as get_db
from app.core.config import settings
from app.core.events_security import verify_events_api_secret
from app.models.events.events_user import EventsUser
from app.models.events.secure_event import SecureEvent
from app.models.events.face_registration import FaceRegistration
from app.models.events.audit_log import EventAuditLog
from app.services.events import register_face, delete_face
from app.services.events.webhook_service import verify_webhook_signature
from engines.base_engine import get_engine
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["BasileaEvents Integration"])


class EventPayload(BaseModel):
    event_id: str
    name: str
    event_date: Optional[datetime] = None
    account_id: str
    namespace: Optional[str] = None


class EventUpdatePayload(BaseModel):
    name: Optional[str] = None
    event_date: Optional[datetime] = None
    status: Optional[str] = None


class FacePayload(BaseModel):
    ticket_id: str
    image_base64: str


class FaceDeletePayload(BaseModel):
    ticket_id: str
    reason: Optional[str] = "deleted_in_source"


class WebhookResponse(BaseModel):
    status: str
    message: str
    processed_at: datetime


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/events", response_model=WebhookResponse)
async def receive_event_webhook(
    request: Request,
    payload: EventPayload,
    db: Session = Depends(get_db)
):
    signature = request.headers.get("X-Secure-Signature", "")
    body = await request.body()
    
    if not verify_webhook_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    existing = db.query(SecureEvent).filter_by(
        external_event_id=payload.event_id
    ).first()
    
    if existing:
        existing.name = payload.name
        existing.event_date = payload.event_date
        if payload.event_date:
            existing.event_date = payload.event_date
        db.commit()
        
        log = EventAuditLog(
            action="webhook.event_updated",
            event_id=str(existing.id),
            actor_type="api",
            extra={"source": "basileia_events", "payload": payload.dict()}
        )
        db.add(log)
        db.commit()
        
        return WebhookResponse(
            status="ok",
            message="Event updated",
            processed_at=datetime.utcnow()
        )
    
    namespace = payload.namespace or f"event_{payload.event_id}"
    
    event = SecureEvent(
        external_event_id=payload.event_id,
        account_id=payload.account_id,
        name=payload.name,
        event_date=payload.event_date,
        namespace=namespace,
        status="active",
        retention_days=90
    )
    
    db.add(event)
    
    log = EventAuditLog(
        action="webhook.event_created",
        event_id=str(event.id),
        actor_type="api",
        extra={"source": "basileia_events", "payload": payload.dict()}
    )
    db.add(log)
    db.commit()
    
    if event.facial_enabled:
        engine = get_engine()
        try:
            await engine.create_collection(event.namespace)
        except Exception as e:
            logger.error(f"Error creating collection: {e}")
    
    return WebhookResponse(
        status="ok",
        message="Event created",
        processed_at=datetime.utcnow()
    )


@router.patch("/events/{external_event_id}", response_model=WebhookResponse)
async def update_event_webhook(
    request: Request,
    external_event_id: str,
    payload: EventUpdatePayload,
    db: Session = Depends(get_db)
):
    signature = request.headers.get("X-Secure-Signature", "")
    
    if not verify_webhook_signature(await request.body(), signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    event = db.query(SecureEvent).filter_by(
        external_event_id=external_event_id
    ).first()
    
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    if payload.name:
        event.name = payload.name
    if payload.event_date:
        event.event_date = payload.event_date
    if payload.status:
        event.status = payload.status
        if payload.status == "ended":
            event.ended_at = datetime.utcnow()
    
    log = EventAuditLog(
        action="webhook.event_updated",
        event_id=str(event.id),
        actor_type="api",
        extra={"source": "basileia_events", "updates": payload.dict()}
    )
    db.add(log)
    db.commit()
    
    return WebhookResponse(
        status="ok",
        message="Event updated",
        processed_at=datetime.utcnow()
    )


@router.delete("/events/{external_event_id}", response_model=WebhookResponse)
async def delete_event_webhook(
    request: Request,
    external_event_id: str,
    db: Session = Depends(get_db)
):
    signature = request.headers.get("X-Secure-Signature", "")
    
    if not verify_webhook_signature(await request.body(), signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    event = db.query(SecureEvent).filter_by(
        external_event_id=external_event_id
    ).first()
    
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    engine = get_engine()
    try:
        await engine.delete_collection(event.namespace)
    except Exception as e:
        logger.error(f"Error deleting collection: {e}")
    
    db.query(FaceRegistration).filter_by(event_id=event.id).update({
        "status": "deleted",
        "deleted_at": datetime.utcnow()
    })
    
    event.status = "deleted"
    event.deleted_at = datetime.utcnow()
    
    log = EventAuditLog(
        action="webhook.event_deleted",
        event_id=str(event.id),
        actor_type="api",
        extra={"source": "basileia_events"}
    )
    db.add(log)
    db.commit()
    
    return WebhookResponse(
        status="ok",
        message="Event deleted",
        processed_at=datetime.utcnow()
    )


@router.post("/events/{external_event_id}/faces", response_model=WebhookResponse)
async def receive_face_webhook(
    request: Request,
    external_event_id: str,
    payload: FacePayload,
    db: Session = Depends(get_db)
):
    signature = request.headers.get("X-Secure-Signature", "")
    
    if not verify_webhook_signature(await request.body(), signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    event = db.query(SecureEvent).filter_by(
        external_event_id=external_event_id
    ).first()
    
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    if not event.facial_enabled:
        return WebhookResponse(
            status="skipped",
            message="Facial recognition not enabled for this event",
            processed_at=datetime.utcnow()
        )
    
    existing = db.query(FaceRegistration).filter_by(
        event_id=event.id,
        ticket_id=payload.ticket_id,
        status="active"
    ).first()
    
    if existing:
        return WebhookResponse(
            status="skipped",
            message="Face already registered",
            processed_at=datetime.utcnow()
        )
    
    result = await register_face(event, payload.ticket_id, payload.image_base64, db)
    
    if result.get("success"):
        return WebhookResponse(
            status="ok",
            message="Face registered",
            processed_at=datetime.utcnow()
        )
    else:
        return WebhookResponse(
            status="error",
            message=f"Face registration failed: {result.get('issues', ['Unknown error'])}",
            processed_at=datetime.utcnow()
        )


@router.delete("/events/{external_event_id}/faces/{ticket_id}", response_model=WebhookResponse)
async def delete_face_webhook(
    request: Request,
    external_event_id: str,
    ticket_id: str,
    payload: FaceDeletePayload = None,
    db: Session = Depends(get_db)
):
    signature = request.headers.get("X-Secure-Signature", "")
    
    if not verify_webhook_signature(await request.body(), signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    event = db.query(SecureEvent).filter_by(
        external_event_id=external_event_id
    ).first()
    
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    reason = payload.reason if payload else "deleted_in_source"
    result = await delete_face(event, ticket_id, reason, db)
    
    return WebhookResponse(
        status="ok" if result.get("success") else "error",
        message=result.get("error") or "Face deleted",
        processed_at=datetime.utcnow()
    )


@router.get("/health")
async def webhook_health():
    return {
        "status": "healthy",
        "service": "basileia_events_webhook",
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/test")
async def webhook_test(
    authorization: str = Header(None)
):
    if authorization != f"Bearer {settings.EVENTS_INTERNAL_API_SECRET}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    return {
        "status": "ok",
        "message": "Webhook endpoint is working",
        "config": {
            "webhook_url_configured": bool(settings.EVENTS_WEBHOOK_URL),
            "internal_secret_configured": bool(settings.EVENTS_INTERNAL_API_SECRET)
        }
    }