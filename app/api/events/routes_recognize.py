from fastapi import APIRouter, Depends, HTTPException, Request, Header, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.core.database import get_db_secure as get_db
from app.core.events_security import get_current_events_user, verify_totem_key
from app.models.events.events_user import EventsUser
from app.models.events.secure_event import SecureEvent
from app.models.events.totem import Totem
from app.services.events import recognize_face, get_event_checkins, get_checkin_stats, get_live_checkins

router = APIRouter(prefix="/recognize", tags=["Recognize"])


class RecognizeRequest(BaseModel):
    image_base64: str


class RecognizeResponse(BaseModel):
    matched: bool
    result: str
    ticket_id: Optional[str] = None
    confidence: Optional[float] = None
    zone: Optional[str] = None
    first_checkin_at: Optional[str] = None


class CheckinResponse(BaseModel):
    id: str
    ticket_id: Optional[str]
    matched: bool
    confidence_score: Optional[float]
    result: str
    attempted_at: datetime

    class Config:
        from_attributes = True


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/events/{event_id}/recognize", response_model=RecognizeResponse)
async def recognize_face_endpoint(
    request: Request,
    event_id: str,
    data: RecognizeRequest,
    x_totem_key: str = Header(...),
    db: Session = Depends(get_db)
):
    event = db.query(SecureEvent).filter_by(id=event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    if event.status != "active":
        raise HTTPException(status_code=400, detail="Event is not active")
    
    if not event.facial_enabled:
        raise HTTPException(status_code=400, detail="Facial recognition is not enabled for this event")
    
    totem = db.query(Totem).filter_by(
        api_key=x_totem_key,
        status="active"
    ).first()
    
    if not totem:
        raise HTTPException(status_code=401, detail="Invalid totem key")
    
    if totem.mode not in ["facial", "both"]:
        raise HTTPException(status_code=400, detail="Totem is not in facial mode")
    
    totem.last_seen_at = datetime.utcnow()
    db.commit()
    
    result = await recognize_face(event, totem, data.image_base64, db)
    
    return RecognizeResponse(**result)


@router.get("/events/{event_id}/checkins", response_model=List[CheckinResponse])
async def get_event_checkins_endpoint(
    request: Request,
    event_id: str,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(get_current_events_user),
    limit: int = 100,
    offset: int = 0
):
    event = db.query(SecureEvent).filter_by(id=event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    checkins = await get_event_checkins(event, db, limit, offset)
    
    return checkins


@router.get("/events/{event_id}/checkins/live")
async def get_live_checkins_endpoint(
    request: Request,
    event_id: str,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(get_current_events_user),
    since: Optional[str] = None
):
    event = db.query(SecureEvent).filter_by(id=event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
        except:
            pass
    
    checkins = await get_live_checkins(event, db, since_dt)
    
    return {
        "event_id": event_id,
        "checkins": [
            {
                "id": c.id,
                "ticket_id": c.ticket_id,
                "matched": c.matched,
                "confidence_score": c.confidence_score,
                "result": c.result,
                "totem_id": c.totem_id,
                "attempted_at": c.attempted_at.isoformat() if c.attempted_at else None
            }
            for c in checkins
        ]
    }


@router.get("/events/{event_id}/stats")
async def get_checkin_stats_endpoint(
    request: Request,
    event_id: str,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(get_current_events_user)
):
    event = db.query(SecureEvent).filter_by(id=event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    stats = await get_checkin_stats(event, db)
    
    return {
        "event_id": event_id,
        **stats
    }