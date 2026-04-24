#!/usr/bin/env python3
"""
Seed script para criar o primeiro admin do Secure Events.
Execute apenas uma vez após as tabelas serem criadas.

Usage: python seed_events_admin.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import SessionSecure
from app.core.config import settings
from app.core.events_security import hash_password
from app.models.events.events_user import EventsUser


def seed_admin():
    db = SessionSecure()
    
    try:
        existing_admin = db.query(EventsUser).filter_by(
            email=settings.EVENTS_ADMIN_EMAIL
        ).first()
        
        if existing_admin:
            print(f"⚠️  Admin já existe: {settings.EVENTS_ADMIN_EMAIL}")
            return
        
        admin = EventsUser(
            name="Admin",
            email=settings.EVENTS_ADMIN_EMAIL,
            password_hash=hash_password(settings.EVENTS_ADMIN_PASSWORD),
            role="events_admin",
            is_active=True
        )
        
        db.add(admin)
        db.commit()
        
        print(f"✅ Admin criado com sucesso!")
        print(f"   Email: {settings.EVENTS_ADMIN_EMAIL}")
        print(f"   Senha: {settings.EVENTS_ADMIN_PASSWORD}")
        print(f"   Role: events_admin")
        print(f"\n⚠️  LEMBRE-SE: Troque a senha após o primeiro login!")
        
    except Exception as e:
        print(f"❌ Erro ao criar admin: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 50)
    print("Secure Events - Seed Admin")
    print("=" * 50)
    seed_admin()