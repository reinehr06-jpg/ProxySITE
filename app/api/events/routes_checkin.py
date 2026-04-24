from fastapi import APIRouter, Depends, HTTPException, Request, Header, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from app.core.database import get_db_secure as get_db
from app.core.events_security import (
    get_current_events_user, verify_totem_key
)
from app.models.events.events_user import EventsUser
from app.models.events.secure_event import SecureEvent
from app.models.events.totem import Totem
from app.services.events import validate_qr_code, get_offline_qr_validations, sync_offline_validations, get_qr_stats

router = APIRouter(prefix="/checkin", tags=["Check-in QR"])


class QRValidationRequest(BaseModel):
    qr_token: str
    device_fingerprint: Optional[str] = None
    geolocation: Optional[dict] = None


class QRValidationResponse(BaseModel):
    valid: bool
    result: str
    ticket_id: Optional[str] = None
    message: Optional[str] = None
    first_use_at: Optional[str] = None


class OfflineValidation(BaseModel):
    ticket_id: str
    totem_id: Optional[str] = None
    device_fingerprint: Optional[str] = None
    ip_address: Optional[str] = None


class OfflineSyncRequest(BaseModel):
    validations: List[OfflineValidation]


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/validate", response_model=QRValidationResponse)
async def validate_qr(
    request: Request,
    event_id: str,
    data: QRValidationRequest,
    x_totem_key: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    event = db.query(SecureEvent).filter_by(id=event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    totem = None
    if x_totem_key:
        totem = db.query(Totem).filter_by(api_key=x_totem_key, status="active").first()
    
    result = await validate_qr_code(
        event=event,
        qr_token=data.qr_token,
        totem=totem,
        device_fingerprint=data.device_fingerprint,
        ip_address=get_client_ip(request),
        geolocation=data.geolocation,
        db=db
    )
    
    return QRValidationResponse(**result)


@router.get("/offline/{event_id}")
async def get_offline_validations(
    request: Request,
    event_id: str,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(get_current_events_user)
):
    event = db.query(SecureEvent).filter_by(id=event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    validations = await get_offline_qr_validations(event, db)
    
    return {
        "event_id": event_id,
        "validations": [
            {
                "ticket_id": v.ticket_id,
                "result": v.result,
                "validated_at": v.validated_at.isoformat() if v.validated_at else None,
                "totem_id": v.totem_id
            }
            for v in validations
        ]
    }


@router.post("/sync")
async def sync_offline(
    request: Request,
    event_id: str,
    data: OfflineSyncRequest,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(get_current_events_user)
):
    event = db.query(SecureEvent).filter_by(id=event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    validations_data = [v.dict() for v in data.validations]
    result = await sync_offline_validations(event, validations_data, db)
    
    return result


@router.get("/stats/{event_id}")
async def get_qr_stats_endpoint(
    request: Request,
    event_id: str,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(get_current_events_user)
):
    event = db.query(SecureEvent).filter_by(id=event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    stats = await get_qr_stats(event, db)
    
    return {
        "event_id": event_id,
        **stats
    }