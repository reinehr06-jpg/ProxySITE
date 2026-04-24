#!/usr/bin/env python3
"""
Script de geração de chaves iniciales para eventos existentes.

Uso:
    python scripts/generate_initial_keys.py
    python scripts/generate_initial_keys.py --event-id={uuid}
    
Gera chaves RSA e Totem para eventos que não têm chaves geradas.
Executar APENAS uma vez em sistemas existentes.
"""

import os
import sys
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


def generate_initial_keys(event_id: str = None) -> dict:
    db = SessionLocal()
    
    try:
        if event_id:
            events = [db.query(SecureEvent).filter_by(id=event_id).first()]
            if not events[0]:
                logger.error(f"Evento não encontrado: {event_id}")
                return {"success": False, "error": "Event not found"}
        else:
            events = db.query(SecureEvent).filter(
                SecureEvent.status == "active"
            ).all()
        
        count = 0
        
        for event in events:
            if event.rsa_private_key_encrypted and event.totem_key_encrypted:
                logger.info(f"⏭️  {event.name}: já tem chaves, pulando")
                continue
            
            logger.info(f"🔑 Gerando chaves para: {event.name}")
            
            if not event.rsa_private_key_encrypted:
                private_pem, public_pem = CryptoService.generate_rsa_keypair()
                event.rsa_private_key_encrypted = CryptoService.encrypt_private_key(private_pem)
            
            if not event.totem_key_encrypted:
                raw_totem_key = os.urandom(32).hex()
                event.totem_key_encrypted = CryptoService.encrypt_data(raw_totem_key)
                event.totem_key_hint = raw_totem_key[:8] + "..."
            
            event.updated_at = datetime.utcnow()
            
            count += 1
            logger.info(f"✅ {event.name}: chaves geradas")
        
        db.commit()
        
        logger.info(f"📊 {count} eventos atualizados com chaves iniciais")
        
        return {
            "success": True,
            "updated": count,
            "total": len(events)
        }
        
    except Exception as e:
        logger.error(f"Erro ao gerar chaves: {e}")
        db.rollback()
        return {"success": False, "error": str(e)}
    finally:
        db.close()


def verify_keys(event_id: str) -> dict:
    db = SessionLocal()
    
    try:
        event = db.query(SecureEvent).filter_by(id=event_id).first()
        
        if not event:
            return {"success": False, "error": "Event not found"}
        
        has_rsa = bool(event.rsa_private_key_encrypted)
        has_totem = bool(event.totem_key_encrypted)
        
        logger.info(f"📋 {event.name}:")
        logger.info(f"   - RSA: {'✅' if has_rsa else '❌'}")
        logger.info(f"   - Totem Key: {'✅' if has_totem else '❌'}")
        
        if has_totem and event.totem_key_hint:
            logger.info(f"   - Hint: {event.totem_key_hint}***")
        
        return {
            "success": True,
            "event_id": event_id,
            "has_rsa_key": has_rsa,
            "has_totem_key": has_totem,
            "totem_key_hint": event.totem_key_hint if has_totem else None
        }
        
    finally:
        db.close()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Geração de chaves iniciais")
    parser.add_argument("--event-id", type=str, help="ID do evento específico")
    parser.add_argument("--verify", type=str, help="Verificar chaves de um evento")
    
    args = parser.parse_args()
    
    if args.verify:
        result = verify_keys(args.verify)
        print(result)
        sys.exit(0 if result.get("success") else 1)
    else:
        result = generate_initial_keys(args.event_id)
        print(result)
        sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()