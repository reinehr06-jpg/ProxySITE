from fastapi import APIRouter, HTTPException, status, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from app.core.database import get_db
from app.core.auth import get_current_user, log_security_event
from app.core.security import get_client_ip, limiter
from app.core.config import settings
from app.core.schemas import IntegrationConfig, WebhookPayload
from app.models.all_models import User, Alert
import requests
import hmac
import hashlib
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["Integrations"])

security = HTTPBearer(auto_error=False)

integration_settings = {
    "uazapi_key": "",
    "basileia_key": "",
    "basileia_webhook": "",
    "uazapi_connected": False,
    "basileia_webhook_active": False
}


def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    if not signature:
        return False
    
    expected_signature = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(f"sha256={expected_signature}", signature)


@router.get("", dependencies=[Depends(get_current_user)])
@limiter.limit("30/minute")
async def get_integrations(request: Request):
    return {
        **integration_settings,
        "uazapi_key": "***" if integration_settings["uazapi_key"] else "",
        "basileia_key": "***" if integration_settings["basileia_key"] else ""
    }


@router.post("", dependencies=[Depends(get_current_user)])
@limiter.limit("20/minute")
async def save_integrations(
    request: Request,
    config: IntegrationConfig,
    current_user: User = Depends(get_current_user)
):
    if config.uazapi_key:
        integration_settings["uazapi_key"] = config.uazapi_key
        try:
            response = requests.get(
                "https://api.uazapi.com/v1/me",
                headers={"token": config.uazapi_key},
                timeout=5
            )
            if response.status_code == 200:
                integration_settings["uazapi_connected"] = True
            else:
                integration_settings["uazapi_connected"] = False
        except:
            integration_settings["uazapi_connected"] = False
    
    if config.basileia_key:
        integration_settings["basileia_key"] = config.basileia_key
    
    if config.basileia_webhook:
        if not config.basileia_webhook.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="Invalid webhook URL")
        integration_settings["basileia_webhook"] = config.basileia_webhook
        integration_settings["basileia_webhook_active"] = True
    
    log_security_event("INTEGRATIONS_UPDATED", current_user.username, "Integration settings changed", get_client_ip(request))
    
    return {"status": "ok", "message": "Configurações salvas"}


@router.post("/test-uazapi", dependencies=[Depends(get_current_user)])
@limiter.limit("10/minute")
async def test_uazapi(request: Request, key: str):
    if not key or len(key) < 10:
        raise HTTPException(status_code=400, detail="Invalid API key")
    
    try:
        response = requests.get(
            "https://api.uazapi.com/v1/me",
            headers={"token": key},
            timeout=10
        )
        if response.status_code == 200:
            return {"status": "ok", "connected": True, "message": "Conexão bem sucedida!"}
        else:
            return {"status": "error", "connected": False, "message": "API Key inválida"}
    except Exception as e:
        return {"status": "error", "connected": False, "message": f"Erro: {str(e)}"}


@router.post("/webhook/basileia")
@limiter.limit("30/minute")
async def basileia_webhook(request: Request):
    client_ip = get_client_ip(request)
    
    if client_ip not in settings.allowed_webhook_ips_list and settings.ENVIRONMENT == "production":
        log_security_event("WEBHOOK_BLOCKED", "unknown", f"Blocked IP: {client_ip}", client_ip)
        raise HTTPException(status_code=403, detail="IP not allowed")
    
    body = await request.body()
    signature = request.headers.get("X-Webhook-Signature", "")
    
    if not verify_webhook_signature(body, signature, settings.WEBHOOK_SECRET):
        if settings.ENVIRONMENT == "production":
            log_security_event("WEBHOOK_INVALID_SIGNATURE", "unknown", f"IP: {client_ip}", client_ip)
            raise HTTPException(status_code=401, detail="Invalid signature")
    
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    event_type = data.get("type", "unknown")
    
    db = next(get_db())
    try:
        alert = Alert(
            id=str(uuid.uuid4()),
            type=event_type,
            message=str(data),
            level="info" if event_type == "success" else "warning"
        )
        db.add(alert)
        db.commit()
        
        if event_type == "client_created":
            pass
        elif event_type == "client_updated":
            pass
        elif event_type == "client_deleted":
            pass
            
        return {"status": "ok"}
    finally:
        db.close()


@router.get("/alerts", dependencies=[Depends(get_current_user)])
@limiter.limit("60/minute")
async def get_alerts(request: Request, limit: int = 50):
    if limit > 100:
        limit = 100
    
    db = next(get_db())
    try:
        alerts = db.query(Alert).order_by(Alert.created_at.desc()).limit(limit).all()
        return [
            {
                "id": a.id,
                "type": a.type,
                "message": a.message,
                "level": a.level,
                "created_at": a.created_at.isoformat() if a.created_at else None
            }
            for a in alerts
        ]
    finally:
        db.close()


@router.get("/cleanup/stats", dependencies=[Depends(get_current_user)])
@limiter.limit("30/minute")
async def get_cleanup_stats(request: Request):
    from datetime import datetime, timedelta
    
    db = next(get_db())
    try:
        six_months_ago = datetime.now() - timedelta(days=180)
        
        inactive_clients = db.query(Client).filter(
            Client.status.in_(["error", "disconnected"]),
            Client.last_switch < six_months_ago
        ).count()
        
        inactive_proxies = db.query(Proxy).filter(
            Proxy.last_check < six_months_ago
        ).count()
        
        old_logs = db.query(Log).filter(
            Log.created_at < six_months_ago
        ).count()
        
        return {
            "inactive_clients": inactive_clients,
            "inactive_proxies": inactive_proxies,
            "old_logs": old_logs
        }
    finally:
        db.close()


@router.post("/cleanup/clean", dependencies=[Depends(get_current_user)])
@limiter.limit("5/minute")
async def clean_old_data(request: Request, current_user: User = Depends(get_current_user)):
    from datetime import datetime, timedelta
    from app.models.all_models import Client, Proxy, Log
    
    db = next(get_db())
    try:
        six_months_ago = datetime.now() - timedelta(days=180)
        
        deleted_clients = 0
        deleted_proxies = 0
        deleted_logs = 0
        
        inactive_clients = db.query(Client).filter(
            Client.status.in_(["error", "disconnected"]),
            Client.last_switch < six_months_ago
        ).all()
        for c in inactive_clients:
            db.delete(c)
            deleted_clients += 1
        
        inactive_proxies = db.query(Proxy).filter(
            Proxy.last_check < six_months_ago
        ).all()
        for p in inactive_proxies:
            db.delete(p)
            deleted_proxies += 1
        
        old_logs = db.query(Log).filter(
            Log.created_at < six_months_ago
        ).all()
        for l in old_logs:
            db.delete(l)
            deleted_logs += 1
        
        db.commit()
        
        log_security_event("DATA_CLEANUP", current_user.username, f"Cleaned: {deleted_clients} clients, {deleted_proxies} proxies, {deleted_logs} logs", get_client_ip(request))
        
        return {
            "status": "ok",
            "message": f"Limpeza concluída: {deleted_clientes} clientes, {deleted_proxies} proxies, {deleted_logs} logs removidos"
        }
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


@router.get("/monitoring/proxy/{proxy_ip}", dependencies=[Depends(get_current_user)])
@limiter.limit("60/minute")
async def get_proxy_logs(request: Request, proxy_ip: str):
    import re
    if not re.match(r'^(\d{1,3}\.){3}\d{1,3}$', proxy_ip):
        raise HTTPException(status_code=400, detail="Invalid IP address format")
    
    db = next(get_db())
    try:
        logs = db.query(NetworkLog).filter(
            NetworkLog.proxy_ip == proxy_ip
        ).order_by(NetworkLog.created_at.desc()).all()
        
        return [
            {
                "id": l.id,
                "method": l.method,
                "endpoint": l.endpoint,
                "status_code": l.status_code,
                "response_time": l.response_time,
                "created_at": l.created_at.isoformat() if l.created_at else None
            }
            for l in logs
        ]
    finally:
        db.close()


import uuid
from app.models.all_models import Client, Proxy, Log, NetworkLog