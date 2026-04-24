from fastapi import HTTPException, Depends, Header, Request
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
from datetime import datetime, timedelta
from typing import Optional
from app.core.config import settings
from app.core.database import get_db_secure
from app.models.events.events_user import EventsUser
from app.models.events.totem import Totem
import hashlib
import logging

logger = logging.getLogger(__name__)

# Simple hash for local testing (without bcrypt)
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(plain: str, hashed: str) -> bool:
    return hashlib.sha256(plain.encode()).hexdigest() == hashed

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/secure-events/api/auth/login"
)


def create_access_token(user_id: str, role: str, account_id: str = None) -> str:
    expire = datetime.utcnow() + timedelta(
        minutes=settings.EVENTS_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": user_id,
        "role": role,
        "scope": "secure_events",
        "exp": expire,
        "iat": datetime.utcnow()
    }
    if account_id:
        payload["account_id"] = account_id
    return jwt.encode(payload, settings.EVENTS_JWT_SECRET, algorithm="HS256")


def create_refresh_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(
        days=settings.EVENTS_REFRESH_TOKEN_EXPIRE_DAYS
    )
    return jwt.encode({
        "sub": user_id,
        "scope": "secure_events_refresh",
        "exp": expire
    }, settings.EVENTS_JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.EVENTS_JWT_SECRET,
            algorithms=["HS256"]
        )
        return payload
    except JWTError as e:
        logger.warning(f"JWT decode error: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")


def validate_cross_system_token(token: str) -> Optional[str]:
    """Valida token cross-system recebido do Proxy"""
    try:
        from app.core.auth import validate_cross_system_token as validate
        return validate(token)
    except Exception as e:
        logger.warning(f"Cross-system token validation error: {e}")
        return None


async def get_current_user_or_cross_system(request: Request):
    """
    Dependência usada nas rotas do Secure Events.
    Aceita tanto JWT quanto cross-system token.
    """
    # 1. Check middleware validated user first
    if hasattr(request.state, 'cross_system_user') and request.state.cross_system_user:
        return {"type": "cross_system", "username": request.state.cross_system_user, "role": "events_admin"}
    
    # 2. Try query param (cross-system token)
    token_param = request.query_params.get("token")
    if token_param:
        username = validate_cross_system_token(token_param)
        if username:
            return {"type": "cross_system", "username": username, "role": "events_admin"}
        else:
            raise HTTPException(
                status_code=500,
                detail="Token inválido ou expirado"
            )
    
    # 3. Try Authorization header (JWT normal do Secure Events)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
        payload = decode_token(token)
        return {"type": "jwt", "user_id": payload.get("sub"), "role": payload.get("role")}
    
    # 4. No token
    raise HTTPException(
        status_code=401,
        detail="Autenticação requerida"
    )


async def get_current_events_user(
    request: Request,
    db = Depends(get_db_secure)
):
    # 1. Check if validated by middleware (cross-system)
    if hasattr(request.state, 'cross_system_user') and request.state.cross_system_user:
        # Create placeholder user for cross-system
        username = request.state.cross_system_user
        user = db.query(EventsUser).filter(
            (EventsUser.email == username) | (EventsUser.name == username)
        ).first()
        if user:
            return user
        # Create temporary user object
        class TempUser:
            def __init__(self, name):
                self.id = name
                self.name = name
                self.email = name
                self.role = "events_admin"
                self.is_active = True
        return TempUser(username)
    
    # 2. Normal JWT
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    payload = decode_token(token)
    
    if payload.get("scope") != "secure_events":
        raise HTTPException(status_code=401, detail="Invalid token scope")
    
    user_id = payload.get("sub")
    
    user = db.query(EventsUser).filter_by(
        id=user_id, is_active=True
    ).first()
    
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    if user.locked_until and user.locked_until > datetime.utcnow():
        raise HTTPException(status_code=423, detail="Account temporarily locked")
    
    return user


def require_role(*roles):
    async def checker(user=Depends(get_current_events_user)):
        if user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail="Insufficient permissions"
            )
        return user
    return checker


async def verify_events_api_secret(authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    if token != settings.EVENTS_INTERNAL_API_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return token


async def verify_totem_key(
    x_totem_key: str = Header(...),
    db = Depends(get_db_secure)
):
    totem = db.query(Totem).filter_by(
        api_key=x_totem_key,
        status="active"
    ).first()
    
    if not totem:
        raise HTTPException(status_code=401, detail="Invalid totem key")
    
    totem.last_seen_at = datetime.utcnow()
    db.commit()
    return totem


def log_security_event(
    event_type: str,
    user_id: str = None,
    details: str = None,
    ip_address: str = None
):
    logger.warning(
        f"SECURE_EVENTS SECURITY: {event_type} | User: {user_id} | IP: {ip_address} | Details: {details}"
    )


async def check_brute_force(
    email: str,
    db
) -> bool:
    user = db.query(EventsUser).filter_by(email=email).first()
    
    if not user:
        return True
    
    if user.locked_until and user.locked_until > datetime.utcnow():
        raise HTTPException(
            status_code=423,
            detail="Account temporarily locked. Try again later."
        )
    
    return True


def increment_failed_attempt(user: EventsUser, db):
    user.failed_attempts += 1
    
    if user.failed_attempts >= settings.EVENTS_MAX_FAILED_ATTEMPTS:
        user.locked_until = datetime.utcnow() + timedelta(
            minutes=settings.EVENTS_LOCKOUT_MINUTES
        )
        log_security_event(
            "ACCOUNT_LOCKED",
            str(user.id),
            f"Locked after {user.failed_attempts} failed attempts"
        )
    
    db.commit()


def reset_failed_attempts(user: EventsUser, db):
    user.failed_attempts = 0
    user.locked_until = None
    db.commit()