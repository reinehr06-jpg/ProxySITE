from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from datetime import datetime
from pydantic import BaseModel
from typing import Optional, List
from app.core.database import get_db_secure as get_db
from app.core.events_security import (
    get_current_events_user, require_role, verify_events_api_secret,
    get_current_user_or_cross_system
)
from app.models.events.events_user import EventsUser
from app.models.events.secure_event import SecureEvent
from app.models.events.audit_log import EventAuditLog
from app.services.events import register_face, delete_face
from engines.base_engine import get_engine
import uuid

router = APIRouter(prefix="/events", tags=["Events"])


class EventCreate(BaseModel):
    external_event_id: str
    account_id: str
    name: str
    event_date: Optional[datetime] = None
    facial_enabled: bool = True
    namespace: Optional[str] = None
    retention_days: int = 90


class EventUpdate(BaseModel):
    name: Optional[str] = None
    event_date: Optional[datetime] = None
    facial_enabled: Optional[bool] = None
    retention_days: Optional[int] = None


class FaceRegisterRequest(BaseModel):
    ticket_id: str
    image_base64: str


class EventResponse(BaseModel):
    id: str
    external_event_id: str
    account_id: str
    name: str
    event_date: Optional[datetime]
    facial_enabled: bool
    namespace: str
    status: str
    retention_days: int
    created_at: datetime
    ended_at: Optional[datetime]

    class Config:
        from_attributes = True


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    request: Request,
    event_data: EventCreate,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(require_role("events_admin", "events_operator"))
):
    namespace = event_data.namespace or f"event_{event_data.external_event_id}"
    
    existing = db.query(SecureEvent).filter(
        SecureEvent.external_event_id == event_data.external_event_id
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Event with this external_event_id already exists"
        )
    
    event = SecureEvent(
        external_event_id=event_data.external_event_id,
        account_id=event_data.account_id,
        name=event_data.name,
        event_date=event_data.event_date,
        facial_enabled=event_data.facial_enabled,
        namespace=namespace,
        retention_days=event_data.retention_days,
        status="active"
    )
    
    db.add(event)
    
    log = EventAuditLog(
        action="event.created",
        event_id=str(event.id),
        actor_type="admin",
        actor_id=str(current_user.id),
        ip_address=get_client_ip(request)
    )
    db.add(log)
    db.commit()
    
    if event_data.facial_enabled:
        engine = get_engine()
        try:
            await engine.create_collection(event.namespace)
        except Exception as e:
            pass
    
    return event


@router.get("", response_model=List[EventResponse])
async def list_events(
    request: Request,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(get_current_events_user),
    status_filter: Optional[str] = None
):
    query = db.query(SecureEvent)
    
    if status_filter:
        query = query.filter_by(status=status_filter)
    else:
        query = query.filter(SecureEvent.status != "deleted")
    
    return query.order_by(SecureEvent.created_at.desc()).all()


@router.get("/{event_id}", response_model=EventResponse)
async def get_event(
    request: Request,
    event_id: str,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(get_current_events_user)
):
    event = db.query(SecureEvent).filter_by(id=event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.patch("/{event_id}", response_model=EventResponse)
async def update_event(
    request: Request,
    event_id: str,
    event_data: EventUpdate,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(require_role("events_admin"))
):
    event = db.query(SecureEvent).filter_by(id=event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    if event_data.name:
        event.name = event_data.name
    if event_data.event_date:
        event.event_date = event_data.event_date
    if event_data.facial_enabled is not None:
        event.facial_enabled = event_data.facial_enabled
    if event_data.retention_days:
        event.retention_days = event_data.retention_days
    
    db.commit()
    db.refresh(event)
    
    log = EventAuditLog(
        action="event.updated",
        event_id=event_id,
        actor_type="admin",
        actor_id=str(current_user.id),
        ip_address=get_client_ip(request)
    )
    db.add(log)
    db.commit()
    
    return event


@router.post("/{event_id}/end", response_model=EventResponse)
async def end_event(
    request: Request,
    event_id: str,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(require_role("events_admin"))
):
    event = db.query(SecureEvent).filter_by(id=event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    if event.status == "ended":
        raise HTTPException(status_code=400, detail="Event already ended")
    
    event.status = "ended"
    event.ended_at = datetime.utcnow()
    
    log = EventAuditLog(
        action="event.ended",
        event_id=event_id,
        actor_type="admin",
        actor_id=str(current_user.id),
        ip_address=get_client_ip(request)
    )
    db.add(log)
    db.commit()
    
    return event


@router.delete("/{event_id}/faces/{ticket_id}")
async def delete_event_face(
    request: Request,
    event_id: str,
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(require_role("events_admin", "events_operator"))
):
    event = db.query(SecureEvent).filter_by(id=event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    result = await delete_face(event, ticket_id, "manual_deletion", db)
    
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Face not found"))
    
    return {"status": "ok", "message": f"Face {ticket_id} deleted"}


@router.delete("/{event_id}/faces")
async def delete_all_event_faces(
    request: Request,
    event_id: str,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(require_role("events_admin"))
):
    event = db.query(SecureEvent).filter_by(id=event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    engine = get_engine()
    try:
        await engine.delete_collection(event.namespace)
    except Exception as e:
        pass
    
    from app.models.events.face_registration import FaceRegistration
    db.query(FaceRegistration).filter_by(event_id=event_id).update({
        "status": "deleted",
        "deleted_at": datetime.utcnow()
    })
    
    log = EventAuditLog(
        action="event.faces_deleted",
        event_id=event_id,
        actor_type="admin",
        actor_id=str(current_user.id),
        ip_address=get_client_ip(request)
    )
    db.add(log)
    db.commit()
    
    return {"status": "ok", "message": f"All faces for event {event_id} deleted"}


@router.get("/{event_id}/stats")
async def get_event_stats(
    request: Request,
    event_id: str,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(get_current_events_user)
):
    event = db.query(SecureEvent).filter_by(id=event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    from app.models.events.face_registration import FaceRegistration
    from app.models.events.checkin_attempt import CheckinAttempt
    from sqlalchemy import func
    
    total_faces = db.query(FaceRegistration).filter_by(
        event_id=event_id,
        status="active"
    ).count()
    
    checkins = db.query(
        func.count(CheckinAttempt.id)
    ).filter(
        CheckinAttempt.event_id == event_id,
        CheckinAttempt.matched == True,
        CheckinAttempt.result == "identified"
    ).scalar() or 0
    
    unique_checkins = db.query(
        func.count(func.distinct(CheckinAttempt.ticket_id))
    ).filter(
        CheckinAttempt.event_id == event_id,
        CheckinAttempt.matched == True,
        CheckinAttempt.result == "identified"
    ).scalar() or 0
    
    return {
        "event_id": event_id,
        "event_name": event.name,
        "status": event.status,
        "total_faces_registered": total_faces,
        "total_checkins": checkins,
        "unique_people_checked_in": unique_checkins,
        "created_at": event.created_at.isoformat() if event.created_at else None,
        "ended_at": event.ended_at.isoformat() if event.ended_at else None
    }