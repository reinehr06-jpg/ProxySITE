from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from app.api import routes_clients, routes_dispatch, routes_integrations, routes_auth
from app.core.database import engine_proxy, engine_secure, Base, init_models
from app.core.security import add_security_middleware, limiter
from app.core.config import settings
from app.core.events_security import validate_cross_system_token
import threading
from app.jobs.monitor_proxies import run_monitoring_loop
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

init_models()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Secure Proxy Microservice for Basileia Church",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Middleware - permitir BasileaEvents
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*"  # em dev permite todos, em prod mudar para domínios específicos
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def secure_events_auth_middleware(request: Request, call_next):
    """Valida token cross-system para todas rotas do Secure Events"""
    path = request.url.path
    
    # Rotas públicas que não precisam de token (APENAS login)
    public_routes = [
"/vault/api/auth/login",
        "/vault/api/auth/register", 
        "/vault/api/auth/refresh",
        "/vault/api/checkin/validate",
        "/vault/api/webhooks/",

        if path.startswith("/vault/") and path.endswith(".html"):

        if path == "/vault/index.html":

        if path.startswith("/vault/api/"):

app.include_router(events_auth_router, prefix="/vault/api", tags=["Basileia Vault - Auth"])
app.include_router(events_events_router, prefix="/vault/api", tags=["Basileia Vault - Events"])
app.include_router(events_faces_router, prefix="/vault/api", tags=["Basileia Vault - Faces"])
app.include_router(events_checkin_router, prefix="/vault/api", tags=["Basileia Vault - Check-in"])
app.include_router(events_recognize_router, prefix="/vault/api", tags=["Basileia Vault - Recognize"])
app.include_router(events_totems_router, prefix="/vault/api", tags=["Basileia Vault - Totems"])
app.include_router(events_logs_router, prefix="/vault/api", tags=["Basileia Vault - Logs"])
app.include_router(events_webhooks_router, prefix="/vault/api", tags=["Basileia Vault - Webhooks"])
app.include_router(events_pairing_router, prefix="/vault/api", tags=["Basileia Vault - Pairing"])

app.mount("/vault", StaticFiles(directory="static/vault", html=True), name="vault")

            "vault": "/vault"
    }


@app.get("/api/health")
async def health_check():
    from datetime import datetime
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}")
    
    if settings.ENVIRONMENT == "production":
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "error_code": "INTERNAL_ERROR"}
        )
    else:
        return JSONResponse(
            status_code=500,
            content={"detail": str(exc), "error_code": "INTERNAL_ERROR"}
        )


def start_scheduler():
    from app.jobs.face_retention import auto_delete_expired_faces
    
    if settings.FACE_AUTO_DELETE:
        scheduler.add_job(
            auto_delete_expired_faces,
            "cron",
            hour=0,
            minute=0,
            id="face_retention"
        )
        logger.info("Face retention job scheduled (daily at midnight)")
    
    scheduler.start()


@app.on_event("startup")
def startup_event():
    logger.info("Starting Proxy Microservice...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    
    # Proxy monitoring thread
    thread = threading.Thread(target=run_monitoring_loop, daemon=True)
    thread.start()
    logger.info("Background monitoring started")
    
    # Start scheduler for Secure Events jobs
    start_scheduler()


@app.on_event("shutdown")
def shutdown_event():
    logger.info("Shutting down Proxy Microservice...")
    scheduler.shutdown()