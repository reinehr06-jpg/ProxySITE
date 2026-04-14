from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import requests

router = APIRouter()

class IntegrationConfig(BaseModel):
    uazapi_key: str = None
    basileia_key: str = None
    basileia_webhook: str = None

# In-memory storage (em produção usar banco de dados)
integration_settings = {
    "uazapi_key": "",
    "basileia_key": "",
    "basileia_webhook": "",
    "uazapi_connected": False,
    "basileia_webhook_active": False
}

@router.get("/integrations")
async def get_integrations():
    """Retorna configurações de integrações"""
    return integration_settings

@router.post("/integrations")
async def save_integrations(config: IntegrationConfig):
    """Salva configurações de integrações"""
    if config.uazapi_key:
        integration_settings["uazapi_key"] = config.uazapi_key
        # Testar conexão com Uazapi
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
        integration_settings["basileia_webhook"] = config.basileia_webhook
        integration_settings["basileia_webhook_active"] = True
    
    return {"status": "ok", "message": "Configurações salvas"}

@router.post("/integrations/test-uazapi")
async def test_uazapi(key: str):
    """Testa conexão com Uazapi"""
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
async def basileia_webhook(data: dict):
    """
    Webhook para receber eventos do Basileia Church
    """
    event_type = data.get("type", "unknown")
    
    # Salvar alerta
    from app.core.database import SessionLocal
    from app.models.all_models import Alert
    
    db = SessionLocal()
    try:
        alert = Alert(
            type=event_type,
            message=str(data),
            level="info" if event_type == "success" else "warning"
        )
        db.add(alert)
        db.commit()
        
        # Processar evento
        if event_type == "client_created":
            # Novo cliente criado - precisa de provisionamento manual
            pass
        elif event_type == "client_updated":
            # Cliente atualizado
            pass
        elif event_type == "client_deleted":
            # Cliente removido
            pass
            
        return {"status": "ok"}
    finally:
        db.close()

@router.get("/alerts")
async def get_alerts(limit: int = 50, level: str = None):
    """Retorna lista de alertas"""
    from app.core.database import SessionLocal
    from app.models.all_models import Alert
    
    db = SessionLocal()
    try:
        query = db.query(Alert).order_by(Alert.created_at.desc())
        if level:
            query = query.filter(Alert.level == level)
        alerts = query.limit(limit).all()
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

@router.get("/cleanup/stats")
async def get_cleanup_stats():
    """Retorna estatísticas para limpeza"""
    from app.core.database import SessionLocal
    from app.models.all_models import Client, Proxy, Log
    from datetime import datetime, timedelta
    
    db = SessionLocal()
    try:
        three_months_ago = datetime.now() - timedelta(days=90)
        
        # Clientes inativos há mais de 3 meses
        inactive_clients = db.query(Client).filter(
            Client.status.in_(["error", "disconnected"]),
            Client.last_switch < three_months_ago
        ).count()
        
        # Proxies sem atividade há mais de 3 meses
        inactive_proxies = db.query(Proxy).filter(
            Proxy.last_check < three_months_ago
        ).count()
        
        # Logs antigos
        old_logs = db.query(Log).filter(
            Log.created_at < three_months_ago
        ).count()
        
        # Proxies sem atividade há mais de 3 meses
        inactive_proxies = db.query(Proxy).filter(
            Proxy.last_check < three_months_ago
        ).count()
        
        return {
            "inactive_clients": inactive_clients,
            "inactive_proxies": inactive_proxies,
            "old_logs": old_logs
        }
    finally:
        db.close()

@router.post("/cleanup/clean")
async def clean_old_data():
    """Limpa dados antigos"""
    from app.core.database import SessionLocal
    from app.models.all_models import Client, Proxy, Log
    from datetime import datetime, timedelta
    
    db = SessionLocal()
    try:
        three_months_ago = datetime.now() - timedelta(days=90)
        
        # Contadores
        deleted_clients = 0
        deleted_proxies = 0
        deleted_logs = 0
        
        # Deletar clientes inativos
        inactive_clients = db.query(Client).filter(
            Client.status.in_(["error", "disconnected"]),
            Client.last_switch < three_months_ago
        ).all()
        for c in inactive_clients:
            db.delete(c)
            deleted_clients += 1
        
        # Deletar proxies sem atividade
        inactive_proxies = db.query(Proxy).filter(
            Proxy.last_check < three_months_ago
        ).all()
        for p in inactive_proxies:
            db.delete(p)
            deleted_proxies += 1
        
        # Deletar logs antigos
        old_logs = db.query(Log).filter(
            Log.created_at < three_months_ago
        ).all()
        for l in old_logs:
            db.delete(l)
            deleted_logs += 1
        
        db.commit()
        
        return {
            "status": "ok",
            "message": f"Limpeza concluída: {deleted_clients} clientes, {deleted_proxies} proxies, {deleted_logs} logs removidos"
        }
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        db.close()

@router.get("/monitoring/proxy/{proxy_ip}")
async def get_proxy_logs(proxy_ip: str):
    """Retorna todos os logs de um proxy específico"""
    from app.core.database import SessionLocal
    from app.models.all_models import NetworkLog
    
    db = SessionLocal()
    try:
        logs = db.query(NetworkLog).filter(
            NetworkLog.proxy_ip == proxy_ip
        ).order_by(NetworkLog.created_at.desc()).all()
        
        return [
            {
                "id": l.id,
                "method": l.method,
                "endpoint": l.endpoint,
                "request_headers": l.request_headers,
                "request_body": l.request_body,
                "response_body": l.response_body,
                "status_code": l.status_code,
                "response_time": l.response_time,
                "error_message": l.error_message,
                "created_at": l.created_at.isoformat() if l.created_at else None
            }
            for l in logs
        ]
    finally:
        db.close()