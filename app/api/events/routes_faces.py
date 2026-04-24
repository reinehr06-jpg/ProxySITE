from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from datetime import datetime
from pydantic import BaseModel
from typing import Optional, List
from app.core.database import get_db_secure as get_db
from app.core.events_security import (
    get_current_events_user, require_role, verify_events_api_secret
)
from app.models.events.events_user import EventsUser
from app.models.events.secure_event import SecureEvent
from app.models.events.face_registration import FaceRegistration
from app.services.events import register_face, delete_face, validate_face_registration, get_event_faces, count_event_faces

router = APIRouter(prefix="/faces", tags=["Faces"])


class FaceRegisterRequest(BaseModel):
    ticket_id: str
    image_base64: str


class FaceRegisterResponse(BaseModel):
    success: bool
    face_registration_id: Optional[str] = None
    issues: Optional[List[str]] = None


class FaceValidationRequest(BaseModel):
    image_base64: str


class FaceValidationResponse(BaseModel):
    valid: bool
    quality_score: Optional[float] = None
    issues: List[str] = []


class FaceResponse(BaseModel):
    id: str
    ticket_id: str
    status: str
    captured_at: datetime
    deleted_at: Optional[datetime]

    class Config:
        from_attributes = True


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/validate", response_model=FaceValidationResponse)
async def validate_face_image(
    request: Request,
    event_id: str,
    data: FaceValidationRequest,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(require_role("events_admin", "events_operator"))
):
    event = db.query(SecureEvent).filter_by(id=event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    if not event.facial_enabled:
        raise HTTPException(status_code=400, detail="Facial recognition is not enabled for this event")
    
    result = await validate_face_registration(event, data.image_base64, db)
    
    return FaceValidationResponse(
        valid=result.get("valid", False),
        quality_score=result.get("quality_score"),
        issues=result.get("issues", [])
    )


@router.post("/{event_id}/faces", response_model=FaceRegisterResponse)
async def register_face_endpoint(
    request: Request,
    event_id: str,
    data: FaceRegisterRequest,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(verify_events_api_secret)
):
    event = db.query(SecureEvent).filter_by(id=event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    if not event.facial_enabled:
        raise HTTPException(status_code=400, detail="Facial recognition is not enabled for this event")
    
    existing = db.query(FaceRegistration).filter_by(
        event_id=event_id,
        ticket_id=data.ticket_id,
        status="active"
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Face already registered for this ticket")
    
    result = await register_face(event, data.ticket_id, data.image_base64, db)
    
    if not result.get("success"):
        return FaceRegisterResponse(
            success=False,
            issues=result.get("issues", ["Unknown error"])
        )
    
    return FaceRegisterResponse(
        success=True,
        face_registration_id=result.get("face_registration_id")
    )


@router.get("/{event_id}/faces/{ticket_id}", response_model=FaceResponse)
async def get_face_by_ticket(
    request: Request,
    event_id: str,
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(get_current_events_user)
):
    event = db.query(SecureEvent).filter_by(id=event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    face = db.query(FaceRegistration).filter_by(
        event_id=event_id,
        ticket_id=ticket_id
    ).first()
    
    if not face:
        raise HTTPException(status_code=404, detail="Face registration not found")
    
    return face


@router.delete("/{event_id}/faces/{ticket_id}")
async def delete_face_endpoint(
    request: Request,
    event_id: str,
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(verify_events_api_secret)
):
    event = db.query(SecureEvent).filter_by(id=event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    result = await delete_face(event, ticket_id, "api_deletion", db)
    
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Face not found"))
    
    return {"status": "ok", "message": f"Face for ticket {ticket_id} deleted"}


@router.get("/{event_id}/faces", response_model=List[FaceResponse])
async def list_event_faces(
    request: Request,
    event_id: str,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(get_current_events_user),
    status_filter: Optional[str] = None
):
    event = db.query(SecureEvent).filter_by(id=event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    faces = await get_event_faces(event, db, status_filter)
    
    return faces


@router.get("/{event_id}/faces/count")
async def count_event_faces_endpoint(
    request: Request,
    event_id: str,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(get_current_events_user),
    status: str = "active"
):
    event = db.query(SecureEvent).filter_by(id=event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    count = await count_event_faces(event, db, status)
    
    return {"event_id": event_id, "count": count}