import time
import datetime
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.all_models import Client, Proxy, Log
from app.services.uazapi_service import uazapi_service
from app.core.redis import is_in_cooldown, set_cooldown

def run_monitoring_loop():
    print("Starting monitoring loop...")
    while True:
        db = SessionLocal()
        try:
            # 1. Verifica Clientes Ativos
            clients = db.query(Client).filter(Client.activated == True).all()
            for client in clients:
                check_client_health(client, db)
                check_original_proxy_restore(client, db)
            
            # 2. Verifica Proxies do Pool
            proxies = db.query(Proxy).all()
            for proxy in proxies:
                # Simpler check for proxies (ping or mock)
                proxy.last_check = datetime.datetime.utcnow()
                db.commit()
                
        except Exception as e:
            print(f"Error in monitoring loop: {e}")
        finally:
            db.close()
        
        time.sleep(60) # Intervalo de 1 minuto conforme requisitado

def check_client_health(client, db: Session):
    # Call Uazapi status
    instance_id = client.phone
    status_data = uazapi_service.get_status(instance_id)
    
    if not status_data or status_data.get("status") != "connected":
        # 🚨 DETECCÇÃO DE FALHA
        print(f"Failure detected for client {client.phone}")
        client.status = "error" # Mark as error for dashboard popup
        db.commit()
        handle_failure(client, db, "Connection offline / Proxy down")

def check_original_proxy_restore(client, db: Session):
    """
    Ele deve tentar voltar ao ip de origem a cada 6 horas
    ele deve enviar um sinal e ver se o ip voltou sozinho
    """
    if not client.original_proxy_id or client.proxy_id == client.original_proxy_id:
        return

    now = datetime.datetime.utcnow()
    # If no attempt time set, or 6 hours passed
    if not client.restore_attempt_at or now > client.restore_attempt_at:
        print(f"Checking original proxy restore for {client.phone}...")
        
        # Check if original proxy is active
        original_proxy = db.query(Proxy).filter(Proxy.id == client.original_proxy_id).first()
        
        if original_proxy and original_proxy.status == "active":
            # Attempt restore
            from app.jobs.auto_healing import perform_auto_heal
            perform_auto_heal(client, db, "Restoration attempt (6h window)", target_proxy_id=client.original_proxy_id)
            
        # Set next check for 6 hours from now
        client.restore_attempt_at = now + datetime.timedelta(hours=6)
        db.commit()

def handle_failure(client, db: Session, reason: str):
    # 9. VALIDAÇÃO ANTES DE AUTO-HEALING
    if not client.activated:
        return

    # COOLDOWN check
    if is_in_cooldown(str(client.id)):
        print(f"Client {client.phone} is in cooldown. Skipping healing.")
        return

    # Trigger Auto-healing
    from app.jobs.auto_healing import perform_auto_heal
    perform_auto_heal(client, db, reason)
