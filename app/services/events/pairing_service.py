import os
import json
import uuid
import httpx
from datetime import datetime, timedelta
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from app.models.events.secure_event import SecureEvent
from app.services.events.crypto_service import CryptoService
import logging

logger = logging.getLogger(__name__)

PAIRING_TOKEN_EXPIRE_MINUTES = 10
PAIRED_SYSTEMS_URL = os.environ.get("EVENTS_WEBHOOK_URL", "").replace("/webhooks", "/pair")


class PairingService:
    
    @classmethod
    def generate_pairing_token(cls, event: SecureEvent) -> Tuple[str, datetime]:
        expires_at = datetime.utcnow() + timedelta(minutes=PAIRING_TOKEN_EXPIRE_MINUTES)
        
        payload = {
            "event_id": str(event.id),
            "type": "pairing_request",
            "exp": expires_at.isoformat(),
            "nonce": uuid.uuid4().hex[:16]
        }
        
        import base64
        token = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
        
        return token, expires_at
    
    @classmethod
    def verify_pairing_token(cls, token: str) -> Optional[dict]:
        import base64
        try:
            payload = json.loads(base64.urlsafe_b64decode(token.encode()).decode())
        except Exception:
            return None
        
        exp = payload.get("exp")
        if exp:
            expiry = datetime.fromisoformat(exp.replace("Z", "+00:00"))
            if datetime.utcnow() > expiry.replace(tzinfo=None):
                return None
        
        if payload.get("type") != "pairing_request":
            return None
        
        return payload
    
    @classmethod
    async def initiate_pairing(
        cls,
        event: SecureEvent,
        system_name: str,
        system_url: str,
        db: Session
    ) -> dict:
        token, expires_at = cls.generate_pairing_token(event)
        
        paired_system = PairedSystem(
            id=str(uuid.uuid4()),
            event_id=event.id,
            system_name=system_name,
            system_url=system_url,
            status="pending",
            pairing_token=token,
            pairing_expires_at=expires_at
        )
        db.add(paired_system)
        db.commit()
        
        cls._send_pairing_request(
            system_url=system_url,
            event_id=str(event.id),
            token=token,
            expires_at=expires_at.isoformat()
        )
        
        return {
            "pairing_token": token,
            "expires_at": expires_at.isoformat(),
            "system_id": paired_system.id
        }
    
    @classmethod
    def _send_pairing_request(
        cls,
        system_url: str,
        event_id: str,
        token: str,
        expires_at: str
    ):
        try:
            from app.core.config import settings
            if not settings.EVENTS_WEBHOOK_URL:
                return
            
            payload = {
                "action": "pairing_request",
                "event_id": event_id,
                "secure_url": settings.EVENTS_WEBHOOK_URL.replace("/webhooks", "/pair"),
                "token": token,
                "expires_at": expires_at
            }
            
            body = json.dumps(payload)
            signature = CryptoService.sign_hmac(payload)
            
            import asyncio
            asyncio.create_task(cls._do_post_request(system_url, body, signature))
        except Exception as e:
            logger.warning(f"Pairing request failed: {e}")
    
    @classmethod
    async def _do_post_request(cls, url: str, body: str, signature: str):
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    url,
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Basileia-Signature": signature
                    },
                    timeout=10.0
                )
        except Exception as e:
            logger.warning(f"Pairing request error: {e}")
    
    @classmethod
    async def confirm_pairing(
        cls,
        event_id: str,
        system_id: str,
        public_key: str,
        db: Session
    ) -> dict:
        paired = db.query(PairedSystem).filter_by(
            id=system_id,
            event_id=event_id,
            status="pending"
        ).first()
        
        if not paired:
            return {"success": False, "error": "Pairing not found or expired"}
        
        paired.public_key = public_key
        paired.status = "paired"
        paired.paired_at = datetime.utcnow()
        
        db.commit()
        
        return {"success": True, "system_id": system_id}
    
    @classmethod
    def get_event_paired_systems(
        cls,
        event: SecureEvent,
        db: Session
    ) -> list:
        return db.query(PairedSystem).filter_by(
            event_id=event.id,
            status="paired"
        ).all()
    
    @classmethod
    def revoke_pairing(
        cls,
        event_id: str,
        system_id: str,
        db: Session
    ) -> dict:
        paired = db.query(PairedSystem).filter_by(
            id=system_id,
            event_id=event_id
        ).first()
        
        if not paired:
            return {"success": False, "error": "System not found"}
        
        paired.status = "revoked"
        paired.revoked_at = datetime.utcnow()
        
        db.commit()
        
        return {"success": True}


class PairedSystem:
    def __init__(
        self,
        id: str,
        event_id: str,
        system_name: str,
        system_url: str,
        status: str,
        pairing_token: str = None,
        pairing_expires_at: datetime = None,
        public_key: str = None,
        paired_at: datetime = None,
        revoked_at: datetime = None
    ):
        self.id = id
        self.event_id = event_id
        self.system_name = system_name
        self.system_url = system_url
        self.status = status
        self.pairing_token = pairing_token
        self.pairing_expires_at = pairing_expires_at
        self.public_key = public_key
        self.paired_at = paired_at
        self.revoked_at = revoked_at


async def create_pairing(
    event_id: str,
    system_name: str,
    system_url: str,
    db: Session
) -> dict:
    event = db.query(SecureEvent).filter_by(id=event_id).first()
    if not event:
        return {"success": False, "error": "Event not found"}
    
    return await PairingService.initiate_pairing(event, system_name, system_url, db)


def get_paired_systems(event_id: str, db: Session) -> list:
    event = db.query(SecureEvent).filter_by(id=event_id).first()
    if not event:
        return []
    
    systems = PairingService.get_event_paired_systems(event, db)
    return [
        {
            "system_id": s.id,
            "system_name": s.system_name,
            "system_url": s.system_url,
            "paired_at": s.paired_at.isoformat() if s.paired_at else None
        }
        for s in systems
    ]


def revoke_pairing(event_id: str, system_id: str, db: Session) -> dict:
    return PairingService.revoke_pairing(event_id, system_id, db)