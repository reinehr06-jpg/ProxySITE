from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.core.database import get_db_secure as get_db
from app.core.events_security import get_current_events_user, require_role
from app.models.events.events_user import EventsUser
from app.models.events.secure_event import SecureEvent
from app.models.events.totem import Totem
from app.services.events import (
    create_totem, get_totem, get_event_totems, update_totem,
    delete_totem, regenerate_totem_key, heartbeat_totem, get_totem_status
)

router = APIRouter(prefix="/totems", tags=["Totems"])


class TotemCreate(BaseModel):
    name: str
    zone: str
    mode: str = "both"


class TotemUpdate(BaseModel):
    name: Optional[str] = None
    zone: Optional[str] = None
    mode: Optional[str] = None
    status: Optional[str] = None


class TotemResponse(BaseModel):
    id: str
    event_id: str
    name: str
    zone: str
    mode: str
    status: str
    last_seen_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class TotemWithKey(TotemResponse):
    api_key: str


class RegenerateKeyResponse(BaseModel):
    totem_id: str
    new_api_key: str


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("", response_model=TotemWithKey, status_code=status.HTTP_201_CREATED)
async def create_totem_endpoint(
    request: Request,
    event_id: str,
    data: TotemCreate,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(require_role("events_admin", "events_operator"))
):
    event = db.query(SecureEvent).filter_by(id=event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    if data.mode not in ["qr", "facial", "both"]:
        raise HTTPException(status_code=400, detail="Invalid mode. Must be qr, facial, or both")
    
    totem = await create_totem(event, data.name, data.zone, data.mode, db)
    
    return TotemWithKey(
        **totem.__dict__,
        api_key=totem.api_key
    )


@router.get("", response_model=List[TotemResponse])
async def list_totems(
    request: Request,
    event_id: str,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(get_current_events_user),
    status_filter: Optional[str] = None
):
    event = db.query(SecureEvent).filter_by(id=event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    totems = await get_event_totems(event, db, status_filter)
    
    return totems


@router.get("/{totem_id}", response_model=TotemResponse)
async def get_totem_endpoint(
    request: Request,
    totem_id: str,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(get_current_events_user)
):
    totem = await get_totem(totem_id, db)
    if not totem:
        raise HTTPException(status_code=404, detail="Totem not found")
    
    return totem


@router.get("/{totem_id}/with-key", response_model=TotemWithKey)
async def get_totem_with_key(
    request: Request,
    totem_id: str,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(require_role("events_admin"))
):
    totem = await get_totem(totem_id, db)
    if not totem:
        raise HTTPException(status_code=404, detail="Totem not found")
    
    return TotemWithKey(
        **totem.__dict__,
        api_key=totem.api_key
    )


@router.patch("/{totem_id}", response_model=TotemResponse)
async def update_totem_endpoint(
    request: Request,
    totem_id: str,
    data: TotemUpdate,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(require_role("events_admin", "events_operator"))
):
    totem = await update_totem(totem_id, data.dict(exclude_unset=True), db)
    if not totem:
        raise HTTPException(status_code=404, detail="Totem not found")
    
    return totem


@router.delete("/{totem_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_totem_endpoint(
    request: Request,
    totem_id: str,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(require_role("events_admin"))
):
    success = await delete_totem(totem_id, db)
    if not success:
        raise HTTPException(status_code=404, detail="Totem not found")


@router.post("/{totem_id}/heartbeat")
async def totem_heartbeat(
    request: Request,
    totem_id: str,
    db: Session = Depends(get_db)
):
    totem = await heartbeat_totem(totem_id, db)
    if not totem:
        raise HTTPException(status_code=404, detail="Totem not found")
    
    return {"status": "ok", "last_seen_at": totem.last_seen_at.isoformat()}


@router.post("/{totem_id}/regenerate-key", response_model=RegenerateKeyResponse)
async def regenerate_totem_key_endpoint(
    request: Request,
    totem_id: str,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(require_role("events_admin"))
):
    result = await regenerate_totem_key(totem_id, db)
    if not result:
        raise HTTPException(status_code=404, detail="Totem not found")
    
    return RegenerateKeyResponse(**result)


@router.get("/status/{event_id}")
async def get_totem_status_endpoint(
    request: Request,
    event_id: str,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(get_current_events_user)
):
    event = db.query(SecureEvent).filter_by(id=event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    status_data = await get_totem_status(event, db)
    
    return {
        "event_id": event_id,
        **status_data
    }