import time

# Memória local caso o Redis falhe
_local_cache = {}

try:
    import redis
    from app.core.config import settings
    if settings.REDIS_URL and settings.REDIS_URL.strip():
        redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        redis_client.ping() # Testa conexão
    else:
        redis_client = None
except Exception:
    redis_client = None

def set_cooldown(client_id: str, seconds: int = 300):
    if redis_client:
        try:
            redis_client.set(f"client:{client_id}:cooldown", 1, ex=seconds)
        except Exception:
             _local_cache[f"cooldown:{client_id}"] = time.time() + seconds
    else:
        _local_cache[f"cooldown:{client_id}"] = time.time() + seconds

def is_in_cooldown(client_id: str) -> bool:
    if redis_client:
        try:
            return redis_client.exists(f"client:{client_id}:cooldown") > 0
        except Exception:
            expiry = _local_cache.get(f"cooldown:{client_id}", 0)
            return time.time() < expiry
    else:
        expiry = _local_cache.get(f"cooldown:{client_id}", 0)
        return time.time() < expiry

def log_failure(proxy_id: str):
    if redis_client:
        try:
            redis_client.incr(f"proxy:{proxy_id}:failures")
        except Exception:
            _local_cache[f"proxy:{proxy_id}:failures"] = _local_cache.get(f"proxy:{proxy_id}:failures", 0) + 1
    else:
        _local_cache[f"proxy:{proxy_id}:failures"] = _local_cache.get(f"proxy:{proxy_id}:failures", 0) + 1

def get_proxy_failures(proxy_id: str) -> int:
    if redis_client:
        try:
            val = redis_client.get(f"proxy:{proxy_id}:failures")
            return int(val) if val else 0
        except Exception:
            return _local_cache.get(f"proxy:{proxy_id}:failures", 0)
    else:
        return _local_cache.get(f"proxy:{proxy_id}:failures", 0)
