from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

SECURE_DB_URL = os.environ.get("SECURE_DATABASE_URL", "")

if not SECURE_DB_URL:
    from app.core.config import settings
    SECURE_DB_URL = settings.SECURE_DATABASE_URL

if SECURE_DB_URL.startswith("sqlite"):
    engine_secure = create_engine(
        SECURE_DB_URL,
        connect_args={"check_same_thread": False}
    )
else:
    engine_secure = create_engine(
        SECURE_DB_URL,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True
    )

SessionSecure = sessionmaker(autocommit=False, autoflush=False, bind=engine_secure)


def get_db_secure():
    """Dependência do banco do Secure Events"""
    db = SessionSecure()
    try:
        yield db
    finally:
        db.close()