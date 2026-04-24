import os
import secrets
from functools import lru_cache
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseModel):
    PROJECT_NAME: str = "Proxy Microservice"
    DATABASE_URL: str = Field(default="")
    SECURE_DATABASE_URL: str = ""  # NOVO - banco separado para Secure Events
    REDIS_URL: str = ""
    SECURE_REDIS_URL: str = ""  # NOVO - redis db separado
    UAZAPI_TOKEN: str = ""
    BASILEIA_API_KEY: str = ""
    
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    
    ALLOWED_WEBHOOK_IPS: str = "127.0.0.1,::1"
    RATE_LIMIT_PER_MINUTE: int = 60
    ENVIRONMENT: str = "development"
    
    WEBHOOK_SECRET: str = ""
    
    # Secure Events Subsystem
    EVENTS_JWT_SECRET: str = ""
    EVENTS_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    EVENTS_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    EVENTS_INTERNAL_API_SECRET: str = ""
    EVENTS_WEBHOOK_SECRET: str = ""
    EVENTS_WEBHOOK_URL: str = ""
    
    # Face Engine
    FACE_ENGINE: str = "aws_rekognition"
    AWS_REKOGNITION_REGION: str = "us-east-1"
    FACE_S3_BUCKET: str = "basileia-secure-faces"
    FACE_S3_PREFIX: str = "events/faces"
    FACE_SIMILARITY_THRESHOLD: float = 0.85
    FACE_MIN_QUALITY_SCORE: float = 0.70
    FACE_RETENTION_DAYS: int = 90
    FACE_AUTO_DELETE: bool = True
    
    # Rate Limiting
    EVENTS_RATE_LIMIT_RECOGNIZE: int = 10
    EVENTS_RATE_LIMIT_CHECKIN: int = 5
    EVENTS_RATE_LIMIT_AUTH: int = 5
    
    # Brute-force protection
    EVENTS_MAX_FAILED_ATTEMPTS: int = 5
    EVENTS_LOCKOUT_MINUTES: int = 15
    
    # Totem
    TOTEM_API_KEY_SALT: str = ""
    
    # Admin seed
    EVENTS_ADMIN_EMAIL: str = "admin@basileia.app"
    EVENTS_ADMIN_PASSWORD: str = "TrocarNaPrimeiraVez@2026"
    
    # Crypto Keys
    SECURE_MASTER_KEY: str = ""
    SECURE_WEBHOOK_SECRET: str = ""
    QR_HMAC_SECRET: str = ""
    
    def __init__(self, **data):
        for field_name, field in self.model_fields.items():
            if field_name in data:
                continue
            env_val = os.environ.get(field_name)
            if env_val:
                data[field_name] = env_val
            elif field.default:
                data[field_name] = field.default
            elif field_name == "DATABASE_URL":
                data[field_name] = "postgresql://postgres:password@localhost:5432/proxy_db"
            elif field_name in ("SECRET_KEY", "WEBHOOK_SECRET", "EVENTS_JWT_SECRET", "EVENTS_INTERNAL_API_SECRET", "EVENTS_WEBHOOK_SECRET", "TOTEM_API_KEY_SALT"):
                data[field_name] = secrets.token_hex(32)
        super().__init__(**data)
    
    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT.lower() == "development"
    
    @property
    def allowed_webhook_ips_list(self) -> list:
        return [ip.strip() for ip in self.ALLOWED_WEBHOOK_IPS.split(",") if ip.strip()]
    
    @property
    def secure_database_url(self) -> str:
        return self.SECURE_DATABASE_URL or os.environ.get("SECURE_DATABASE_URL", "")
    
    @property
    def secure_redis_url(self) -> str:
        return self.SECURE_REDIS_URL or os.environ.get("SECURE_REDIS_URL", "redis://localhost:6379/1")


class DatabaseSettings(BaseModel):
    DATABASE_URL: str = ""
    POOL_SIZE: int = 5
    MAX_OVERFLOW: int = 10
    
    def __init__(self, **data):
        for field_name, field in self.model_fields.items():
            if field_name in data:
                continue
            env_val = os.environ.get(field_name)
            if env_val:
                data[field_name] = env_val
            elif field.default is not None:
                data[field_name] = field.default
            elif field_name == "DATABASE_URL":
                data[field_name] = "postgresql://postgres:password@localhost:5432/proxy_db"
        super().__init__(**data)


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
db_settings = DatabaseSettings()