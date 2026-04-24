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
        "/secure-events/api/auth/login",
        "/secure-events/api/auth/register", 
        "/secure-events/api/auth/refresh",
        "/secure-events/api/checkin/validate",
        "/secure-events/api/webhooks/",
        "/docs",
        "/redoc",
        "/openapi.json"
    ]
    
    # Verifica exacte match para rotas públicas
    for public in public_routes:
        if path == public:
            return await call_next(request)
    
    # Pages HTML precisam token (exceto login)
    if path.startswith("/secure-events/") and path.endswith(".html"):
        # Login page is public
        if path == "/secure-events/index.html":
            return await call_next(request)
        
        # Other pages need token
        token = request.query_params.get("token")
        if token:
            username = validate_cross_system_token(token)
            if username:
                request.state.cross_system_user = username
                return await call_next(request)
        
        return JSONResponse(
            status_code=500,
            content={"detail": "Token requerido. Acesse pelo Dashboard do Proxy."}
        )
    
    # API precisa token
    if path.startswith("/secure-events/api/"):
        token = request.query_params.get("token")
        if token:
            username = validate_cross_system_token(token)
            if username:
                request.state.cross_system_user = username
                return await call_next(request)
        
        return JSONResponse(
            status_code=500,
            content={"detail": "Token inválido ou expirado"}
        )
    
    return await call_next(request)

app.state.limiter = limiter
add_security_middleware(app)

app.include_router(routes_auth.router, prefix="/api", tags=["Authentication"])
app.include_router(routes_clients.router, prefix="/api", tags=["Clients"])
app.include_router(routes_dispatch.router, prefix="/api", tags=["Dispatch"])
app.include_router(routes_integrations.router, prefix="/api", tags=["Integrations"])

# Secure Events Subsystem Routes
from app.api.events import (
    events_auth_router,
    events_events_router,
    events_faces_router,
    events_checkin_router,
    events_recognize_router,
    events_totems_router,
    events_logs_router,
    events_webhooks_router,
    events_pairing_router
)

app.include_router(events_auth_router, prefix="/secure-events/api", tags=["Secure Events - Auth"])
app.include_router(events_events_router, prefix="/secure-events/api", tags=["Secure Events - Events"])
app.include_router(events_faces_router, prefix="/secure-events/api", tags=["Secure Events - Faces"])
app.include_router(events_checkin_router, prefix="/secure-events/api", tags=["Secure Events - Check-in"])
app.include_router(events_recognize_router, prefix="/secure-events/api", tags=["Secure Events - Recognize"])
app.include_router(events_totems_router, prefix="/secure-events/api", tags=["Secure Events - Totems"])
app.include_router(events_logs_router, prefix="/secure-events/api", tags=["Secure Events - Logs"])
app.include_router(events_webhooks_router, prefix="/secure-events/api", tags=["Secure Events - Webhooks"])
app.include_router(events_pairing_router, prefix="/secure-events/api", tags=["Secure Events - Pairing"])

# Static files for Secure Events frontend
app.mount("/dashboard", StaticFiles(directory="static", html=True), name="static")
app.mount("/secure-events", StaticFiles(directory="static/secure-events", html=True), name="secure-events")

# Scheduler for jobs
scheduler = AsyncIOScheduler()


@app.get("/")
async def root():
    return {
        "message": "Proxy Microservice API is running",
        "docs": "/docs",
        "dashboard": "/dashboard",
        "secure_events": "/secure-events"
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