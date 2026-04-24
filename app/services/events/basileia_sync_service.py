import httpx
from datetime import datetime
from typing import Optional, List, Dict
from app.core.config import settings
from app.services.events.webhook_service import send_webhook
import logging

logger = logging.getLogger(__name__)


class BasileaEventsSync:
    def __init__(self):
        self.base_url = settings.EVENTS_WEBHOOK_URL.replace("/webhooks/facial-checkin", "")
        self.api_secret = settings.EVENTS_INTERNAL_API_SECRET
        self.webhook_secret = settings.EVENTS_WEBHOOK_SECRET
    
    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_secret}",
            "Content-Type": "application/json",
            "X-Secure-Signature": self.webhook_secret
        }
    
    async def sync_event_to_basileia(self, event_data: dict) -> bool:
        if not self.base_url:
            logger.warning("BasileaEvents URL not configured")
            return False
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/events/sync",
                    json=event_data,
                    headers=self._get_headers(),
                    timeout=10.0
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Error syncing event to BasileaEvents: {e}")
            return False
    
    async def get_events_from_basileia(self) -> List[dict]:
        if not self.base_url:
            return []
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/events",
                    headers=self._get_headers(),
                    timeout=10.0
                )
                if response.status_code == 200:
                    return response.json()
        except Exception as e:
            logger.error(f"Error getting events from BasileaEvents: {e}")
        
        return []
    
    async def full_sync(self) -> dict:
        synced = 0
        failed = 0
        
        events = await self.get_events_from_basileia()
        
        for event in events:
            result = await self.sync_event_to_basileia(event)
            if result:
                synced += 1
            else:
                failed += 1
        
        return {
            "synced": synced,
            "failed": failed,
            "total": len(events),
            "timestamp": datetime.utcnow().isoformat()
        }


async def create_event_in_basileia(event_data: dict) -> bool:
    sync = BasileaEventsSync()
    return await sync.sync_event_to_basileia(event_data)


async def get_basileia_events() -> List[dict]:
    sync = BasileaEventsSync()
    return await sync.get_events_from_basileia()


async def full_sync_with_basileia() -> dict:
    sync = BasileaEventsSync()
    return await sync.full_sync()