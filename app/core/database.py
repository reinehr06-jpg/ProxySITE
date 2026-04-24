from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings, db_settings
import os

# ============== ENGINE DO PROXY (existente) ==============
# Support both PostgreSQL and SQLite
if settings.DATABASE_URL.startswith("sqlite"):
    engine_proxy = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
    if settings.DATABASE_URL.startswith("sqlite"):
        @event.listens_for(engine_proxy, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
else:
    engine_proxy = create_engine(
        settings.DATABASE_URL,
        pool_size=db_settings.POOL_SIZE,
        max_overflow=db_settings.MAX_OVERFLOW,
        pool_pre_ping=True
    )

# ============== ENGINE DO SECURE EVENTS (NOVO - separado) ==============
secure_db_url = os.environ.get("SECURE_DATABASE_URL", "")
if not secure_db_url:
    secure_db_url = settings.SECURE_DATABASE_URL

# Padrão: fallback para engine_proxy se não configurado
engine_secure = engine_proxy

if secure_db_url and not secure_db_url.startswith("postgresql://postgres:password@localhost"):
    if secure_db_url.startswith("sqlite"):
        engine_secure = create_engine(
            secure_db_url,
            connect_args={"check_same_thread": False}
        )
    else:
        engine_secure = create_engine(
            secure_db_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True
        )

# Session makers
SessionProxy = sessionmaker(autocommit=False, autoflush=False, bind=engine_proxy)
SessionSecure = sessionmaker(autocommit=False, autoflush=False, bind=engine_secure)

# Alias for backwards compatibility
SessionLocal = SessionProxy

# ============== EXPORTS FOR BACKWARDS COMPATIBILITY ==============
engine = engine_proxy  # Alias
Base = declarative_base()


def get_db():
    """Dependência do banco do proxy"""
    db = SessionProxy()
    try:
        yield db
    finally:
        db.close()

def get_db_secure():
    """Dependência do banco do Secure Events - tenta separado, fallback para proxy"""
    db = SessionSecure()
    try:
        yield db
    finally:
        db.close()


def init_models():
    from app.models.all_models import User, Client, Proxy, Log, NetworkLog, Alert
    from app.models.events import (
        EventsUser, SecureEvent, FaceRegistration,
        CheckinAttempt, QRValidation, Totem, EventAuditLog,
        PairedSystem
    )
    # Cria todas as tabelas no banco do proxy
    Base.metadata.create_all(bind=engine_proxy)
    
    # Cria tabelas do Secure Events no banco separado (se configurado)
    if engine_secure != engine_proxy:
        Base.metadata.create_all(bind=engine_secure)
    
    print("✅ Modelos inicializados em ambos os bancos")


# Exports
__all__ = [
    "engine_proxy",
    "engine_secure", 
    "engine",  # backwards compatibility
    "SessionProxy",
    "SessionSecure", 
    "SessionLocal",  # backwards compatibility
    "Base",
    "get_db",
    "get_db_secure",
    "init_models"
]