from sqlalchemy import Column, String, Boolean, DateTime, Float, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.core.database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)

class Client(Base):
    __tablename__ = "clients"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    phone = Column(String, unique=True, index=True)
    church_name = Column(String, nullable=True)
    cpf_cnpj = Column(String, nullable=True)
    basileia_id = Column(String, nullable=True)
    default_ip = Column(String, nullable=True)
    proxy_id = Column(String, ForeignKey("proxies.id"), nullable=True)
    original_proxy_id = Column(String, nullable=True)
    status = Column(String, default="pending") 
    activated = Column(Boolean, default=False)
    estado = Column(String, nullable=True)
    cidade = Column(String, nullable=True)
    last_switch = Column(DateTime, nullable=True)
    restore_attempt_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

class Proxy(Base):
    __tablename__ = "proxies"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    ip = Column(String, unique=True)
    device_model = Column(String, default="Unknown Device")
    device_id = Column(String, nullable=True)
    bairro = Column(String)
    cidade = Column(String)
    estado = Column(String)
    lat = Column(Float)
    lng = Column(Float)
    status = Column(String, default="active")
    last_check = Column(DateTime, nullable=True)
    avg_response_time = Column(Float, default=0.0)
    fail_count = Column(Integer, default=0)
    request_count = Column(Integer, default=0)

class Log(Base):
    __tablename__ = "logs"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id = Column(String, ForeignKey("clients.id"))
    old_proxy = Column(String)
    new_proxy = Column(String)
    reason = Column(String)
    created_at = Column(DateTime, server_default=func.now())

class NetworkLog(Base):
    __tablename__ = "network_logs"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    proxy_ip = Column(String, index=True)
    method = Column(String) 
    endpoint = Column(String)
    status_code = Column(Integer)
    response_time = Column(Float)
    created_at = Column(DateTime, server_default=func.now())

class Alert(Base):
    __tablename__ = "alerts"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    type = Column(String)
    message = Column(String)
    level = Column(String, default="info")  # info, warning, error, success
    created_at = Column(DateTime, server_default=func.now())
