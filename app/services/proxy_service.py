from sqlalchemy.orm import Session
from app.models.all_models import Proxy, Client
from sqlalchemy import or_

class ProxyService:
    @staticmethod
    def find_best_proxy(db: Session, client_id: str):
        client = db.query(Client).filter(Client.id == client_id).first()
        if not client:
            return None

        # Get original proxy info for location if available, otherwise we use client's requested phone location (mocked here)
        # Assuming we have a way to match client location. Let's assume the client table/proxy table has location info.
        # For simplicity, let's assume we find a proxy by location proximity.
        
        # User's Logic:
        # 1. Mesma bairro
        # 2. Mesma cidade
        # 3. Mesma estado
        # 4. Qualquer proxy disponível
        
        # We need a reference proxy or location to compare.
        # Let's assume we have 'target_location' info.
        current_proxy = db.query(Proxy).filter(Proxy.id == client.proxy_id).first()
        if not current_proxy:
            # Fallback to any active proxy if no current proxy info
            return db.query(Proxy).filter(Proxy.status == "active").first()

        # 1. Bairro
        proxy = db.query(Proxy).filter(
            Proxy.bairro == current_proxy.bairro,
            Proxy.status == "active",
            Proxy.id != current_proxy.id
        ).first()
        if proxy: return proxy

        # 2. Cidade
        proxy = db.query(Proxy).filter(
            Proxy.cidade == current_proxy.cidade,
            Proxy.status == "active",
            Proxy.id != current_proxy.id
        ).first()
        if proxy: return proxy

        # 3. Estado
        proxy = db.query(Proxy).filter(
            Proxy.estado == current_proxy.estado,
            Proxy.status == "active",
            Proxy.id != current_proxy.id
        ).first()
        if proxy: return proxy

        # 4. Any
        proxy = db.query(Proxy).filter(
            Proxy.status == "active",
            Proxy.id != current_proxy.id
        ).first()
        if proxy: return proxy

        return "UAZAPI_FALLBACK"

proxy_service = ProxyService()
