from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.api import routes_clients, routes_dispatch, routes_integrations, routes_auth
from app.core.database import engine_proxy, engine_secure, Base, init_models
from app.core.security import add_security_middleware, limiter
from app.core.config import settings
from app.core.auth import validate_page_token, get_username_from_session
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

init_models()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Basileia Proxy + Vault",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def page_token_auth_middleware(request: Request, call_next):
    """Valida token por página para todas rotas protegidas"""
    path = request.url.path
    
    # Rotas públicas (sem token)
    public_routes = [
        "/",
        "/login.html",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/api/health",
        "/api/auth/login",
        "/api/auth/captcha",
        "/api/auth/register",
    ]
    public_routes_vault = [
        "/vault/",
        "/vault/index.html",
        "/vault/login.html",
        "/vault/api/auth/login",
        "/vault/api/auth/captcha", 
        "/vault/api/auth/register",
    ]
    
    # Verifica se é rota pública
    is_public = False
    for route in public_routes:
        if path == route or path.startswith(route + "/"):
            is_public = True
            break
    
    for route in public_routes_vault:
        if path == route or path.startswith(route + "/"):
            is_public = True
            break
    
    if is_public:
        return await call_next(request)
    
    # Para páginas html (não API), precisa token
    if path.endswith(".html"):
        page_token = request.query_params.get("token")
        session_token = request.query_params.get("session")
        
        # Validar token de página
        if page_token and session_token:
            # Extrai nome da página do path
            page = path.rstrip(".html").lstrip("/")
            if validate_page_token(session_token, page, page_token):
                return await call_next(request)
        
        # Sem token - acesso negado
        return JSONResponse(
            status_code=403,
            content={"detail": "Token requerido. Faça login primeiro."}
        )
    
    # Para API, usa header Authorization
    return await call_next(request)


# Routers do Proxy
app.include_router(routes_auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(routes_clients.router, prefix="/api", tags=["Clients"])
app.include_router(routes_dispatch.router, prefix="/api", tags=["Dispatch"])
app.include_router(routes_integrations.router, prefix="/api", tags=["Integrations"])

# Vault routers
from app.api.events import (
    events_auth_router, events_events_router, events_faces_router,
    events_checkin_router, events_recognize_router, events_totems_router,
    events_logs_router, events_webhooks_router, events_pairing_router
)

app.include_router(events_auth_router, prefix="/vault/api/auth", tags=["Vault - Auth"])
app.include_router(events_events_router, prefix="/vault/api", tags=["Vault - Events"])
app.include_router(events_faces_router, prefix="/vault/api", tags=["Vault - Faces"])
app.include_router(events_checkin_router, prefix="/vault/api", tags=["Vault - Check-in"])
app.include_router(events_recognize_router, prefix="/vault/api", tags=["Vault - Recognize"])
app.include_router(events_totems_router, prefix="/vault/api", tags=["Vault - Totems"])
app.include_router(events_logs_router, prefix="/vault/api", tags=["Vault - Logs"])
app.include_router(events_webhooks_router, prefix="/vault/api", tags=["Vault - Webhooks"])
app.include_router(events_pairing_router, prefix="/vault/api", tags=["Vault - Pairing"])

# Static files
app.mount("/", StaticFiles(directory="static", html=True), name="static")


@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/")
async def root():
    return {
        "message": "Basileia API",
        "docs": "/docs",
        "login": "/login.html",
        "vault": "/vault/",
    }


@app.get("/api/health")
async def health_check():
    from datetime import datetime
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


# Health check and startup
logger.info("Starting Basileia Microservice...")