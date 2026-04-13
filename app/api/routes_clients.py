from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import get_db
from app.models.all_models import Client, Proxy, Log, User, NetworkLog
from app.core.auth import get_password_hash
import uuid
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/clients")
async def list_clients(db: Session = Depends(get_db)):
    return db.query(Client).all()

@router.get("/stats")
async def get_stats(db: Session = Depends(get_db)):
    try:
        total_clients = db.query(Client).count()
        active_clients = db.query(Client).filter(Client.status == "active").count()
        fallen_clients = db.query(Client).filter(Client.status.in_(["error", "disconnected"])).all()
        total_proxies = db.query(Proxy).count()
        active_proxies = db.query(Proxy).filter(Proxy.status == "active").count()
        
        # New Metrics
        proxies = db.query(Proxy).all()
        avg_resp = db.query(func.avg(Proxy.avg_response_time)).scalar() or 0
        uazapi_ok = True # Mock connection status
        
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
            "recent_logs": logs
        }
    except Exception as e:
        logger.error(f"Stats Error: {e}")
        return {"error": str(e)}

@router.get("/proxies/{proxy_id}/clients")
async def get_proxy_clients(proxy_id: str, db: Session = Depends(get_db)):
    clients = db.query(Client).filter(Client.proxy_id == proxy_id).all()
    return clients

@router.post("/reallocate")
async def reallocate_client(data: dict, db: Session = Depends(get_db)):
    client_id = data.get("client_id")
    new_proxy_id = data.get("new_proxy_id")
    
    client = db.query(Client).filter(Client.id == client_id).first()
    new_proxy = db.query(Proxy).filter(Proxy.id == new_proxy_id).first()
    
    if not client or not new_proxy:
        raise HTTPException(status_code=404, detail="Client or Proxy not found")
        
    old_proxy_ip = client.default_ip
    client.proxy_id = new_proxy.id
    client.default_ip = new_proxy.ip
    
    # Log the reallocation
    db.add(Log(
        client_id=client.id,
        old_proxy=old_proxy_ip,
        new_proxy=new_proxy.ip,
        reason="Manual Admin Reallocation"
    ))
    db.commit()
    return {"status": "ok", "message": f"Client moved to {new_proxy.device_model} ({new_proxy.ip})"}

@router.get("/addresses")
async def get_addresses(db: Session = Depends(get_db)):
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
            "requests": p.request_count
        })
    return result

@router.post("/seed")
async def seed_data(db: Session = Depends(get_db)):
    try:
        # 1. Clear tables in correct order
        db.query(Log).delete()
        db.query(NetworkLog).delete()
        db.query(Client).delete()
        db.query(Proxy).delete()
        db.commit()

        # 2. Add New Data
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
        db.flush() # Ensure IDs are available

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
            
            # Simulated history logs
            if status == "active":
                db.add(Log(client_id=c.id, old_proxy="0.0.0.0", new_proxy=target_proxy.ip, reason="Initial provisioning"))
        
        # Add Alerts for demo
        from app.models.all_models import Alert
        alerts_data = [
            ("client_offline", "Basileia RJ Norte caiu - falha na conexão proxy", "error"),
            ("client_active", "Basileia SC Itapema conectado com sucesso", "success"),
            ("proxy_error", "Proxy 192.168.1.102 não responde há 5 minutos", "error"),
            ("system_warning", "Uso de memória acima de 80%", "warning"),
            ("integration_ok", "Uazapi API responds successfully", "success"),
            ("client_disconnected", "Basileia BH Savassi desconectado", "error"),
            ("backup_complete", "Backup automático concluído", "success"),
        ]
        for alert_type, msg, level in alerts_data:
            db.add(Alert(type=alert_type, message=msg, level=level))

        # Add Network Logs for all proxies
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
        return {"status": "ok", "message": "Enterprise simulation seeded successfully."}
    except Exception as e:
        db.rollback()
        logger.error(f"Seed Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
