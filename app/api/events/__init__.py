from app.api.events.routes_auth import router as events_auth_router
from app.api.events.routes_events import router as events_events_router
from app.api.events.routes_faces import router as events_faces_router
from app.api.events.routes_checkin import router as events_checkin_router
from app.api.events.routes_recognize import router as events_recognize_router
from app.api.events.routes_totems import router as events_totems_router
from app.api.events.routes_logs import router as events_logs_router
from app.api.events.routes_webhooks import router as events_webhooks_router
from app.api.events.routes_pairing import router as events_pairing_router

__all__ = [
    "events_auth_router",
    "events_events_router",
    "events_faces_router",
    "events_checkin_router",
    "events_recognize_router",
    "events_totems_router",
    "events_logs_router",
    "events_webhooks_router",
    "events_pairing_router",
]