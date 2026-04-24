import hmac
import hashlib
import json
import httpx
from datetime import datetime
from typing import Optional
from app.core.config import settings
from app.services.events.crypto_service import CryptoService
import logging

logger = logging.getLogger(__name__)


async def send_webhook(event: str, payload: dict, retry: int = 0) -> bool:
    if not settings.EVENTS_WEBHOOK_URL:
        logger.warning(f"Webhook URL not configured, skipping {event}")
        return False
    
    body = json.dumps({
        "event": event,
        "payload": payload,
        "timestamp": int(datetime.utcnow().timestamp())
    })
    
    signature = CryptoService.sign_hmac({"event": event, "payload": payload})

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.EVENTS_WEBHOOK_URL,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Basileia-Signature": signature
                },
                timeout=10.0
            )
            
            if response.status_code >= 200 and response.status_code < 300:
                logger.info(f"Webhook sent successfully: {event}")
                return True
            else:
                logger.warning(f"Webhook failed: {event} - Status: {response.status_code}")
                return False
                
    except httpx.TimeoutException:
        logger.error(f"Webhook timeout: {event}")
        if retry < 2:
            logger.info(f"Retrying webhook {event} (attempt {retry + 1})")
            return await send_webhook(event, payload, retry + 1)
        return False
    except Exception as e:
        logger.error(f"Webhook error: {event} - {str(e)}")
        return False


async def send_webhook_async(event: str, payload: dict):
    import asyncio
    asyncio.create_task(send_webhook(event, payload))


async def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    if not signature or not settings.EVENTS_WEBHOOK_SECRET:
        return False
    
    expected_signature = hmac.new(
        settings.EVENTS_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(f"sha256={expected_signature}", signature)


class WebhookPayload:
    def __init__(self, event: str, payload: dict):
        self.event = event
        self.payload = payload
        self.timestamp = int(datetime.utcnow().timestamp())
    
    def to_json(self) -> str:
        return json.dumps({
            "event": self.event,
            "payload": self.payload,
            "timestamp": self.timestamp
        })
    
    def get_signature(self) -> str:
        return hmac.new(
            settings.EVENTS_WEBHOOK_SECRET.encode(),
            self.to_json().encode(),
            hashlib.sha256
        ).hexdigest()