from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
import re


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=100)
    
    @validator('username')
    def username_alphanumeric(cls, v):
        if not re.match(r'^[a-zA-Z0-9_]+$', v):
            raise ValueError('Username must be alphanumeric')
        return v.lower()
    
    @validator('password')
    def password_strength(cls, v):
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one number')
        return v


class UserLogin(BaseModel):
    username: str = Field(..., min_length=3)
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class ClientBase(BaseModel):
    phone: str = Field(..., min_length=10, max_length=20)
    church_name: Optional[str] = None
    cpf_cnpj: Optional[str] = None
    basileia_id: Optional[str] = None
    default_ip: Optional[str] = None
    estado: Optional[str] = None
    cidade: Optional[str] = None
    
    @validator('phone')
    def validate_phone(cls, v):
        cleaned = re.sub(r'[^\d]', '', v)
        if len(cleaned) < 10 or len(cleaned) > 13:
            raise ValueError('Invalid phone number')
        return cleaned
    
    @validator('cpf_cnpj')
    def validate_cpf_cnpj(cls, v):
        if v:
            cleaned = re.sub(r'[^\d]', '', v)
            if len(cleaned) not in [11, 14]:
                raise ValueError('Invalid CPF or CNPJ')
        return v


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    church_name: Optional[str] = None
    basileia_id: Optional[str] = None
    default_ip: Optional[str] = None
    status: Optional[str] = None


class ClientResponse(ClientBase):
    id: str
    proxy_id: Optional[str] = None
    original_proxy_id: Optional[str] = None
    status: str = "pending"
    activated: bool = False
    last_switch: Optional[datetime] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class ProxyBase(BaseModel):
    ip: str = Field(..., pattern=r'^(\d{1,3}\.){3}\d{1,3}$')
    device_model: str = Field(..., min_length=1, max_length=100)
    device_id: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    estado: Optional[str] = Field(None, max_length=2)
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lng: Optional[float] = Field(None, ge=-180, le=180)
    
    @validator('ip')
    def validate_ip(cls, v):
        parts = v.split('.')
        if len(parts) != 4:
            raise ValueError('Invalid IP address')
        for part in parts:
            if int(part) > 255:
                raise ValueError('Invalid IP address')
        return v
    
    @validator('estado')
    def validate_estado(cls, v):
        if v and len(v) != 2:
            raise ValueError('Estado must be 2 characters (UF)')
        return v.upper() if v else v


class ProxyCreate(ProxyBase):
    pass


class ProxyUpdate(BaseModel):
    device_model: Optional[str] = None
    status: Optional[str] = None
    fail_count: Optional[int] = None


class ProxyResponse(ProxyBase):
    id: str
    status: str = "active"
    last_check: Optional[datetime] = None
    avg_response_time: float = 0.0
    fail_count: int = 0
    request_count: int = 0
    
    class Config:
        from_attributes = True


class ReallocateRequest(BaseModel):
    client_id: str = Field(..., min_length=1)
    new_proxy_id: str = Field(..., min_length=1)


class IntegrationConfig(BaseModel):
    uazapi_key: Optional[str] = None
    basileia_key: Optional[str] = None
    basileia_webhook: Optional[str] = None
    
    @validator('basileia_webhook')
    def validate_webhook_url(cls, v):
        if v and not v.startswith(('http://', 'https://')):
            raise ValueError('Webhook URL must start with http:// or https://')
        return v


class WebhookPayload(BaseModel):
    type: str = Field(..., min_length=1)
    data: dict = Field(default_factory=dict)
    signature: Optional[str] = None
    timestamp: Optional[str] = None


class DispatchRequest(BaseModel):
    client_id: str = Field(..., min_length=1)
    force: bool = False


class DispatchResponse(BaseModel):
    status: str
    message: str
    client_id: str
    proxy_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AlertResponse(BaseModel):
    id: str
    type: str
    message: str
    level: str
    created_at: datetime


class StatsResponse(BaseModel):
    total_clients: int
    active_clients_count: int
    fallen_clients: List[ClientResponse] = []
    total_proxies: int
    active_proxies: int
    avg_system_response: float
    uazapi_connected: bool
    proxies_by_state: dict
    recent_logs: List[dict]


class HealthCheckResponse(BaseModel):
    status: str
    timestamp: datetime
    version: str = "1.0.0"
    database: str
    redis: Optional[str] = None


class ErrorResponse(BaseModel):
    detail: str
    error_code: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)