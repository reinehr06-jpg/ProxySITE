import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    PROJECT_NAME: str = "Proxy Microservice"
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5433/proxy_db")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6380/0")
    UAZAPI_TOKEN: str = os.getenv("UAZAPI_TOKEN", "")
    BASILEIA_API_KEY: str = os.getenv("BASILEIA_API_KEY", "")

settings = Settings()
