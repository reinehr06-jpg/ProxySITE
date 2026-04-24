"""
Redis client para o Secure Events - usa database 1 separado do proxy
"""
import time
import os

# Memória local caso o Redis falhe
_local_cache = {}

# try:
import redis
from app.core.config import settings
secure_redis_url = os.environ.get("SECURE_REDIS_URL", "")
if not secure_redis_url:
    secure_redis_url = settings.SECURE_REDIS_URL

if secure_redis_url and secure_redis_url.strip():
    try:
        redis_secure = redis.from_url(secure_redis_url, decode_responses=True)
        redis_secure.ping()
    except Exception:
        redis_secure = None
else:
    redis_secure = None
# except Exception:
#     redis_secure = None


def set_qr_used(ticket_id: str, window: int, ttl: int = 3600):
    """Marca QR como usado (anti-replay)"""
    if redis_secure:
        try:
            key = f"qr:used:{ticket_id}:{window}"
            redis_secure.set(key, "1", ex=ttl)
        except Exception:
            _local_cache[key] = time.time() + ttl
    else:
        _local_cache[f"qr:used:{ticket_id}:{window}"] = time.time() + ttl


def is_qr_used(ticket_id: str, window: int) -> bool:
    """Verifica se QR já foi usado"""
    if redis_secure:
        try:
            key = f"qr:used:{ticket_id}:{window}"
            return redis_secure.exists(key) > 0
        except Exception:
            expiry = _local_cache.get(key, 0)
            return time.time() < expiry
    else:
        expiry = _local_cache.get(f"qr:used:{ticket_id}:{window}", 0)
        return time.time() < expiry


def set_facial_cooldown(totem_id: str, seconds: int = 10):
    """Rate limiting para reconhecimento facial"""
    if redis_secure:
        try:
            redis_secure.set(f"totem:{totem_id}:cooldown", 1, ex=seconds)
        except Exception:
            _local_cache[f"totem:{totem_id}:cooldown"] = time.time() + seconds
    else:
        _local_cache[f"totem:{totem_id}:cooldown"] = time.time() + seconds


def is_facial_on_cooldown(totem_id: str) -> bool:
    """Verifica se totem está em cooldown"""
    if redis_secure:
        try:
            return redis_secure.exists(f"totem:{totem_id}:cooldown") > 0
        except Exception:
            expiry = _local_cache.get(f"totem:{totem_id}:cooldown", 0)
            return time.time() < expiry
    else:
        expiry = _local_cache.get(f"totem:{totem_id}:cooldown", 0)
        return time.time() < expiry


def get_redis_secure():
    """Retorna o cliente Redis (para injeções)"""
    return redis_secure


def get_redis_db():
    """Retorna o database number"""
    return 1