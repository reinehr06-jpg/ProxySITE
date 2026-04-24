from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.core.database import get_db_secure as get_db
from app.core.events_security import get_current_events_user
from app.models.events.events_user import EventsUser
from app.models.events.secure_event import SecureEvent
from app.models.events.paired_system import PairedSystem
from app.services.events.pairing_service import create_pairing, get_paired_systems, revoke_pairing
from app.services.events.crypto_service import CryptoService
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pairing", tags=["Pairing"])


class PairingRequest(BaseModel):
    system_name: str
    system_url: str


class PairingConfirmRequest(BaseModel):
    system_id: str
    public_key: str


class PairingResponse(BaseModel):
    success: bool
    pairing_token: Optional[str] = None
    expires_at: Optional[str] = None
    system_id: Optional[str] = None
    error: Optional[str] = None


class PairedSystemResponse(BaseModel):
    system_id: str
    system_name: str
    system_url: str
    paired_at: Optional[str] = None


@router.post("/systems", response_model=PairingResponse)
async def request_pairing(
    event_id: str,
    data: PairingRequest,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(get_current_events_user)
):
    event = db.query(SecureEvent).filter_by(id=event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    result = await create_pairing(event_id, data.system_name, data.system_url, db)
    
    return PairingResponse(**result)


@router.get("/systems")
async def list_paired_systems(
    event_id: str,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(get_current_events_user)
):
    event = db.query(SecureEvent).filter_by(id=event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    systems = get_paired_systems(event_id, db)
    return {"systems": systems}


@router.delete("/systems/{system_id}")
async def remove_paired_system(
    event_id: str,
    system_id: str,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(get_current_events_user)
):
    result = revoke_pairing(event_id, system_id, db)
    
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    
    return result


@router.post("/confirm")
async def confirm_pairing(
    event_id: str,
    data: PairingConfirmRequest,
    db: Session = Depends(get_db)
):
    from app.services.events.pairing_service import PairingService
    
    result = await PairingService.confirm_pairing(event_id, data.system_id, data.public_key, db)
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    
    return result


@router.get("/public-key")
async def get_public_key(
    event_id: str,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(get_current_events_user)
):
    event = db.query(SecureEvent).filter_by(id=event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    private_pem, public_pem = CryptoService.generate_rsa_keypair()
    
    if not hasattr(event, 'rsa_private_key_encrypted') or not event.rsa_private_key_encrypted:
        event.rsa_private_key_encrypted = CryptoService.encrypt_private_key(private_pem)
        db.commit()
    
    return {
        "event_id": event_id,
        "public_key": public_pem
    }


@router.post("/pair")
async def pairing_endpoint(
    event_id: str,
    token: str,
    public_key: str,
    db: Session = Depends(get_db)
):
    from app.services.events.pairing_service import PairingService
    
    token_data = PairingService.verify_pairing_token(token)
    if not token_data:
        raise HTTPException(status_code=400, detail="Invalid or expired pairing token")
    
    if token_data.get("event_id") != event_id:
        raise HTTPException(status_code=400, detail="Token does not match event")
    
    paired = db.query(PairedSystem).filter_by(
        event_id=event_id,
        pairing_token=token,
        status="pending"
    ).first()
    
    if not paired:
        raise HTTPException(status_code=400, detail="Pairing not found")
    
    paired.public_key = public_key
    paired.status = "paired"
    paired.paired_at = datetime.utcnow()
    db.commit()
    
    return {"success": True, "message": "Systems paired successfully"}