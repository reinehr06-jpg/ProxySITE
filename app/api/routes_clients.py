from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import get_db
from app.core.auth import get_current_user, log_security_event
from app.core.security import get_client_ip, limiter
from app.core.schemas import (
    ClientCreate, ClientUpdate, ClientResponse,
    ProxyResponse, ReallocateRequest,
    StatsResponse, ErrorResponse
)
from app.models.all_models import Client, Proxy, Log, User, NetworkLog
import uuid
import logging

router = APIRouter(prefix="", tags=["Clients"])
logger = logging.getLogger(__name__)


@router.get("/clients", response_model=list[ClientResponse])
@limiter.limit("60/minute")
async def list_clients(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    clients = db.query(Client).all()
    return clients


@router.get("/clients/{client_id}", response_model=ClientResponse)
@limiter.limit("60/minute")
async def get_client(
    request: Request,
    client_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.post("/clients", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def create_client(
    request: Request,
    client_data: ClientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    existing = db.query(Client).filter(Client.phone == client_data.phone).first()
    if existing:
        raise HTTPException(status_code=400, detail="Client with this phone already exists")
    
    client = Client(
        id=str(uuid.uuid4()),
        phone=client_data.phone,
        church_name=client_data.church_name,
        cpf_cnpj=client_data.cpf_cnpj,
        basileia_id=client_data.basileia_id,
        default_ip=client_data.default_ip,
        estado=client_data.estado,
        cidade=client_data.cidade,
        status="pending",
        activated=False
    )
    
    db.add(client)
    db.commit()
    db.refresh(client)
    
    log_security_event("CLIENT_CREATED", current_user.username, f"Client: {client.id}", get_client_ip(request))
    
    return client


@router.put("/clients/{client_id}", response_model=ClientResponse)
@limiter.limit("30/minute")
async def update_client(
    request: Request,
    client_id: str,
    client_data: ClientUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    if client_data.church_name is not None:
        client.church_name = client_data.church_name
    if client_data.basileia_id is not None:
        client.basileia_id = client_data.basileia_id
    if client_data.default_ip is not None:
        client.default_ip = client_data.default_ip
    if client_data.status is not None:
        client.status = client_data.status
    
    db.commit()
    db.refresh(client)
    
    log_security_event("CLIENT_UPDATED", current_user.username, f"Client: {client.id}", get_client_ip(request))
    
    return client


@router.delete("/clients/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
async def delete_client(
    request: Request,
    client_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    db.delete(client)
    db.commit()
    
    log_security_event("CLIENT_DELETED", current_user.username, f"Client: {client_id}", get_client_ip(request))


@router.get("/stats", response_model=StatsResponse)
@limiter.limit("60/minute")
async def get_stats(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        total_clients = db.query(Client).count()
        active_clients = db.query(Client).filter(Client.status == "active").count()
        fallen_clients = db.query(Client).filter(Client.status.in_(["error", "disconnected"])).all()
        total_proxies = db.query(Proxy).count()
        active_proxies = db.query(Proxy).filter(Proxy.status == "active").count()
        
        proxies = db.query(Proxy).all()
        avg_resp = db.query(func.avg(Proxy.avg_response_time)).scalar() or 0
        uazapi_ok = True
        
        proxies_by_state = db.query(Proxy.estado, func.count(Proxy.id)).filter(Proxy.status == "active").group_by(Proxy.estado).all()
        proxies_by_state_dict = {state: count for state, count in proxies_by_state if state}
        logs = db.query(Log).order_by(Log.created_at.desc()).limit(10).all()
        
        return {
            "total_clients": total_clients,
            "active_clients_count": active_clients,
            "fallen_clients": fallen_clients,
            "total_proxies": total_proxies,
            "active_proxies": active_proxies,
            "avg_system_response": round(float(avg_resp), 1),
            "uazapi_connected": uazapi_ok,
            "proxies_by_state": proxies_by_state_dict,
            "recent_logs": [
                {
                    "id": l.id,
                    "client_id": l.client_id,
                    "old_proxy": l.old_proxy,
                    "new_proxy": l.new_proxy,
                    "reason": l.reason,
                    "created_at": l.created_at
                } for l in logs
            ]
        }
    except Exception as e:
        logger.error(f"Stats Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/proxies/{proxy_id}/clients")
@limiter.limit("60/minute")
async def get_proxy_clients(
    request: Request,
    proxy_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    clients = db.query(Client).filter(Client.proxy_id == proxy_id).all()
    return [
        {
            "id": c.id,
            "phone": c.phone,
            "church_name": c.church_name,
            "status": c.status,
            "activated": c.activated
        }
        for c in clients
    ]


@router.post("/reallocate")
@limiter.limit("20/minute")
async def reallocate_client(
    request: Request,
    data: ReallocateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    client = db.query(Client).filter(Client.id == data.client_id).first()
    new_proxy = db.query(Proxy).filter(Proxy.id == data.new_proxy_id).first()
    
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    if not new_proxy:
        raise HTTPException(status_code=404, detail="Proxy not found")
    
    old_proxy_ip = client.default_ip
    client.proxy_id = new_proxy.id
    client.default_ip = new_proxy.ip
    
    db.add(Log(
        client_id=client.id,
        old_proxy=old_proxy_ip or "None",
        new_proxy=new_proxy.ip,
        reason=f"Manual Admin Reallocation by {current_user.username}"
    ))
    db.commit()
    
    log_security_event("CLIENT_REALLOCATED", current_user.username, f"Client: {client.id} -> Proxy: {new_proxy.id}", get_client_ip(request))
    
    return {"status": "ok", "message": f"Client moved to {new_proxy.device_model} ({new_proxy.ip})"}


@router.get("/addresses")
@limiter.limit("60/minute")
async def get_addresses(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    proxies = db.query(Proxy).all()
    result = []
    for p in proxies:
        client_count = db.query(Client).filter(Client.proxy_id == p.id).count()
        result.append({
            "id": str(p.id),
            "ip": p.ip,
            "device": p.device_model,
            "clients_count": client_count,
            "status": p.status,
            "avg_response": p.avg_response_time,
            "requests": p.request_count,
            "estado": p.estado,
            "cidade": p.cidade
        })
    return result


@router.post("/seed")
@limiter.limit("5/minute")
async def seed_data(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        db.query(Log).delete()
        db.query(NetworkLog).delete()
        db.query(Client).delete()
        db.query(Proxy).delete()
        db.query(User).delete()
        db.commit()
        # 2. Add New Data
        # Add Admin User
        from app.core.auth import get_password_hash
        admin_user = User(
            id=str(uuid.uuid4()),
            username="Proxy.adm@Basileia.global",
            hashed_password=get_password_hash("1kPiJXL$0m#jAzbUaSN9ttWSFUAf7hbnJ2w1&Us6"),
            is_active=True
        )
        db.add(admin_user)
        states = [
            ("SC", "Joinville", "Samsung Galaxy S23", -26.30, -48.84),
            ("SP", "São Paulo", "iPhone 15 Pro", -23.55, -46.63),
            ("RJ", "Rio de Janeiro", "Motorola Edge 40", -22.90, -43.17),
            ("PR", "Curitiba", "Xiaomi 13T", -25.42, -49.27),
            ("MG", "Belo Horizonte", "Pixel 8 Pro", -19.91, -43.93),
            ("RS", "Porto Alegre", "Samsung Galaxy Fold 5", -30.03, -51.21),
            ("BA", "Salvador", "iPhone 14 Plus", -12.97, -38.50)
        ]
        
        proxies = []
        for i, (st, city, device, lat, lng) in enumerate(states):
            p = Proxy(
                id=str(uuid.uuid4()),
                ip=f"192.168.1.{100 + i}",
                device_model=device,
                device_id=f"DEV-UX-{1000 + i}",
                bairro="Centro",
                cidade=city,
                estado=st,
                lat=lat,
                lng=lng,
                status="active",
                avg_response_time=25.5 + i,
                request_count=100 + (i * 10)
            )
            db.add(p)
            proxies.append(p)
        db.flush()
        
        churches = [
            ("Basileia Matriz Joinville", "SC", "active"),
            ("Basileia SP Sul", "SP", "active"),
            ("Basileia RJ Norte (Offline)", "RJ", "error"),
            ("Basileia Curitiba Centro", "PR", "active"),
            ("Basileia BH Savassi", "MG", "disconnected"),
            ("Basileia RS Moinhos", "RS", "active"),
            ("Basileia BA Pelourinho", "BA", "active"),
            ("Basileia SC Itapema", "SC", "active")
        ]
        
        for i, (name, st, status) in enumerate(churches):
            target_proxy = proxies[i % len(proxies)]
            c = Client(
                id=str(uuid.uuid4()),
                phone=f"4799{1000000 + i}",
                church_name=name,
                cpf_cnpj=f"32.987.654/0001-0{i}",
                basileia_id=f"BC-{9000 + i}",
                default_ip=target_proxy.ip,
                proxy_id=target_proxy.id,
                original_proxy_id=target_proxy.id,
                status=status,
                activated=True,
                estado=st,
                cidade="Simu-City"
            )
            db.add(c)
            
            if status == "active":
                db.add(Log(client_id=c.id, old_proxy="0.0.0.0", new_proxy=target_proxy.ip, reason="Initial provisioning"))
        
        for p in proxies:
            for j in range(5):
                db.add(NetworkLog(
                    proxy_ip=p.ip,
                    method="GET" if j % 2 == 0 else "POST",
                    endpoint=f"/v1/stats/{j}",
                    status_code=200,
                    response_time=0.08
                ))
        
        db.commit()
        
        log_security_event("DATA_SEEDED", current_user.username, "Database seeded with demo data", get_client_ip(request))
        
        return {"status": "ok", "message": "Enterprise simulation seeded successfully."}
    except Exception as e:
        db.rollback()
        logger.error(f"Seed Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))