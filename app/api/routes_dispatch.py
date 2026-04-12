from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.all_models import Client, Proxy, Log
from app.services.uazapi_service import uazapi_service
from app.core.config import settings
import datetime

router = APIRouter()

@router.post("/dispatch/{client_id}")
async def manual_dispatch(client_id: str, db: Session = Depends(get_db)):
    """
    6. DISPATCH MANUAL (PRIMEIRA VEZ)
    - O sistema SÓ pode fazer auto-healing se o cliente já tiver sido ativado manualmente
    - Monta payload, envia para Uazapi, salva conexão
    - activated = true, status = active
    """
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Get proxy associated with this client (or find one)
    proxy = db.query(Proxy).filter(Proxy.id == client.proxy_id).first()
    if not proxy:
        # For the first time, maybe we assign a random available proxy if one isn't set
        proxy = db.query(Proxy).filter(Proxy.status == "active").first()
        if not proxy:
            # Fallback to UAZAPI default if no proxies in DB
            proxy_url = "FALLBACK"
        else:
            proxy_url = f"http://{proxy.ip}"
            client.proxy_id = proxy.id
    else:
        proxy_url = f"http://{proxy.ip}"

    # Integrainca com Uazapi
    # instance_id is assumed to be related to client (e.g., client.phone or a custom field)
    instance_id = client.phone 
    
    result = uazapi_service.set_proxy(instance_id, proxy_url)
    
    if result:
        # Success!
        client.activated = True
        client.status = "active"
        client.last_switch = datetime.datetime.utcnow()
        
        # Guardar proxy original para restauração automática futura
        if not client.original_proxy_id:
            client.original_proxy_id = proxy.id
            # Próxima tentativa de restauração em 6 horas (opcional, já que ele é o original)
        
        # Log the activation
        new_log = Log(
            client_id=client.id,
            old_proxy="None",
            new_proxy=proxy_url,
            reason="Initial Manual Dispatch"
        )
        db.add(new_log)
        db.commit()
        
        return {"status": "ok", "message": "Manual dispatch successful. Auto-healing enabled.", "uazapi_response": result}
    else:
        raise HTTPException(status_code=500, detail="Failed to connect via Uazapi")
