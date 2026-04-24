from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.auth import get_current_user, log_security_event
from app.core.security import get_client_ip, limiter
from app.models.all_models import Client, Proxy, Log, User
from app.services.uazapi_service import uazapi_service
from app.core.config import settings
from app.core.schemas import DispatchRequest, DispatchResponse
import datetime

router = APIRouter(prefix="/dispatch", tags=["Dispatch"])


@router.post("/{client_id}", response_model=DispatchResponse)
@limiter.limit("30/minute")
async def manual_dispatch(
    request: Request,
    client_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from app.models.all_models import User
    
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    proxy = db.query(Proxy).filter(Proxy.id == client.proxy_id).first()
    if not proxy:
        proxy = db.query(Proxy).filter(Proxy.status == "active").first()
        if not proxy:
            proxy_url = "FALLBACK"
        else:
            proxy_url = f"http://{proxy.ip}"
            client.proxy_id = proxy.id
    else:
        proxy_url = f"http://{proxy.ip}"
    
    instance_id = client.phone 
    
    result = uazapi_service.set_proxy(instance_id, proxy_url)
    
    if result:
        client.activated = True
        client.status = "active"
        client.last_switch = datetime.datetime.utcnow()
        
        if not client.original_proxy_id:
            client.original_proxy_id = proxy.id if proxy else None
        
        new_log = Log(
            client_id=client.id,
            old_proxy="None",
            new_proxy=proxy_url,
            reason=f"Initial Manual Dispatch by {current_user.username}"
        )
        db.add(new_log)
        db.commit()
        
        log_security_event("DISPATCH_SUCCESS", current_user.username, f"Client: {client.id}", get_client_ip(request))
        
        return DispatchResponse(
            status="ok",
            message="Manual dispatch successful. Auto-healing enabled.",
            client_id=client.id,
            proxy_id=proxy.id if proxy else None
        )
    else:
        log_security_event("DISPATCH_FAILED", current_user.username, f"Client: {client.id}", get_client_ip(request))
        raise HTTPException(status_code=500, detail="Failed to connect via Uazapi")


@router.post("/auto/{client_id}")
@limiter.limit("30/minute")
async def auto_dispatch(
    request: Request,
    client_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from app.models.all_models import User
    
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    if not client.activated:
        raise HTTPException(status_code=400, detail="Client must be manually activated first")
    
    available_proxies = db.query(Proxy).filter(
        Proxy.status == "active",
        Proxy.id != client.original_proxy_id
    ).all()
    
    if not available_proxies:
        raise HTTPException(status_code=404, detail="No alternative proxies available")
    
    target_proxy = available_proxies[0]
    old_proxy_id = client.proxy_id
    
    client.proxy_id = target_proxy.id
    client.default_ip = target_proxy.ip
    client.last_switch = datetime.datetime.utcnow()
    
    db.add(Log(
        client_id=client.id,
        old_proxy=client.default_ip,
        new_proxy=target_proxy.ip,
        reason=f"Auto-healing: {target_proxy.device_model}"
    ))
    
    db.commit()
    
    log_security_event("AUTO_HEALING", current_user.username, f"Client: {client.id} -> Proxy: {target_proxy.id}", get_client_ip(request))
    
    return {
        "status": "ok",
        "message": f"Auto-healing: Client moved to {target_proxy.device_model}",
        "old_proxy": old_proxy_id,
        "new_proxy": target_proxy.id
    }


@router.get("/history/{client_id}")
@limiter.limit("60/minute")
async def get_dispatch_history(
    request: Request,
    client_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from app.models.all_models import User
    
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    logs = db.query(Log).filter(Log.client_id == client_id).order_by(Log.created_at.desc()).all()
    
    return [
        {
            "id": l.id,
            "old_proxy": l.old_proxy,
            "new_proxy": l.new_proxy,
            "reason": l.reason,
            "created_at": l.created_at.isoformat() if l.created_at else None
        }
        for l in logs
    ]