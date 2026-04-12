import datetime
from sqlalchemy.orm import Session
from app.models.all_models import Client, Proxy, Log
from app.services.proxy_service import proxy_service
from app.services.uazapi_service import uazapi_service
from app.core.redis import set_cooldown

def perform_auto_heal(client, db: Session, reason: str, target_proxy_id=None):
    """
    🧠 10. AUTO-HEALING (SE ATIVADO)
    - Busca o melhor proxy (Bairro -> Cidade -> Estado -> Any)
    - Troca automática no Uazapi
    - Reconexão automática
    - Notificação (Log)
    """
    print(f"Starting auto-heal for client {client.phone} (Reason: {reason})")
    
    old_proxy_url = "UNKNOWN"
    current_proxy = db.query(Proxy).filter(Proxy.id == client.proxy_id).first()
    if current_proxy:
        old_proxy_url = current_proxy.ip

    # 1. Encontrar melhor proxy ou usar o alvo (restauração)
    if target_proxy_id:
        new_proxy = db.query(Proxy).filter(Proxy.id == target_proxy_id).first()
    else:
        new_proxy = proxy_service.find_best_proxy(db, str(client.id))
    
    if not new_proxy:
        print("No proxy available for healing.")
        return

    # 2. Aplicar troca
    if new_proxy == "UAZAPI_FALLBACK":
        proxy_url = "UAZAPI_FALLBACK"
        new_proxy_id = None
    else:
        proxy_url = f"http://{new_proxy.ip}"
        new_proxy_id = new_proxy.id

    # 3. Request Uazapi
    instance_id = client.phone
    result = uazapi_service.set_proxy(instance_id, proxy_url)
    
    if result:
        # 4. Atualizar Cliente
        client.proxy_id = new_proxy_id
        client.status = "active"
        client.last_switch = datetime.datetime.utcnow()
        
        # 5. Salvar Log
        new_log = Log(
            client_id=client.id,
            old_proxy=old_proxy_url,
            new_proxy=proxy_url,
            reason=reason
        )
        db.add(new_log)
        
        # 6. Set Cooldown (5 minutos = 300s) - Only if not a restoration attempt
        if not target_proxy_id:
            set_cooldown(str(client.id), 300)
        
        db.commit()
        print(f"Auto-heal complete for {client.phone}. New proxy: {proxy_url}")
        
        # 7. Reconectar
        uazapi_service.reconnect(instance_id)
    else:
        print(f"Failed to apply auto-heal for {client.phone}")
        client.status = "error"
        db.commit()
