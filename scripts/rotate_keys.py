#!/usr/bin/env python3
"""
Script de rotação de chaves para eventos do Secure Events.

Uso:
    python scripts/rotate_keys.py --event-id={uuid}
    python scripts/rotate_keys.py --all  # Rotacionar todas as chaves
    
O script gera novas chaves RSA e Totem para o evento especificado.
As chaves antigas são descartadas após a rotação bem-sucedida.
"""

import os
import sys
import argparse
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal, engine, Base
from app.models.events.secure_event import SecureEvent
from app.services.events.crypto_service import CryptoService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def rotate_event_keys(event_id: str) -> dict:
    db = SessionLocal()
    
    try:
        event = db.query(SecureEvent).filter_by(id=event_id).first()
        
        if not event:
            logger.error(f"Evento não encontrado: {event_id}")
            return {"success": False, "error": "Event not found"}
        
        logger.info(f"🌐 Rotacionando chaves para evento: {event.name} ({event_id})")
        
        new_private_pem, new_public_pem = CryptoService.generate_rsa_keypair()
        event.rsa_private_key_encrypted = CryptoService.encrypt_private_key(new_private_pem)
        
        raw_totem_key = os.urandom(32).hex()
        event.totem_key_encrypted = CryptoService.encrypt_data(raw_totem_key)
        event.totem_key_hint = raw_totem_key[:8] + "..."
        
        event.updated_at = datetime.utcnow()
        
        db.commit()
        
        logger.info(f"✅ Chaves rotacionadas com sucesso para {event.name}")
        
        return {
            "success": True,
            "event_id": event_id,
            "event_name": event.name,
            "rsa_public_key": new_public_pem[:100] + "...",
            "totem_key_hint": event.totem_key_hint
        }
        
    except Exception as e:
        logger.error(f"Erro ao rotacionar chaves: {e}")
        db.rollback()
        return {"success": False, "error": str(e)}
    finally:
        db.close()


def rotate_all_keys() -> dict:
    db = SessionLocal()
    
    try:
        events = db.query(SecureEvent).filter(
            SecureEvent.status == "active"
        ).all()
        
        rotated = 0
        failed = 0
        
        for event in events:
            try:
                new_private_pem, new_public_pem = CryptoService.generate_rsa_keypair()
                event.rsa_private_key_encrypted = CryptoService.encrypt_private_key(new_private_pem)
                
                raw_totem_key = os.urandom(32).hex()
                event.totem_key_encrypted = CryptoService.encrypt_data(raw_totem_key)
                event.totem_key_hint = raw_totem_key[:8] + "..."
                
                event.updated_at = datetime.utcnow()
                
                rotated += 1
                logger.info(f"✅ {event.name}: chaves rotacionadas")
                
            except Exception as e:
                logger.error(f"❌ {event.name}: {e}")
                failed += 1
        
        db.commit()
        
        logger.info(f"📊 Rotação concluída: {rotated} exitosos, {failed} falhos")
        
        return {
            "success": True,
            "rotated": rotated,
            "failed": failed
        }
        
    except Exception as e:
        logger.error(f"Erro na rotação global: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Rotação de chaves do Secure Events")
    parser.add_argument("--event-id", type=str, help="ID do evento para rotacionar chaves")
    parser.add_argument("--all", action="store_true", help="Rotacionar todas as chaves ativas")
    
    args = parser.parse_args()
    
    if args.event_id:
        result = rotate_event_keys(args.event_id)
        print(result)
        sys.exit(0 if result.get("success") else 1)
    elif args.all:
        result = rotate_all_keys()
        print(result)
        sys.exit(0 if result.get("success") else 1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()