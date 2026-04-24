from datetime import datetime, timedelta
from typing import Optional, List, Dict
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, HTTPBearer
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.config import settings
from app.models.all_models import User
import logging
import time
import secrets
import string

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
security = HTTPBearer()

# Token store (in production use Redis)
# Format: {session_token: {"username": "x", "expires": datetime, "pages": {page_id: page_token}}}
SESSION_TOKENS: Dict = {}


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=7)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def create_cross_system_token(username: str) -> str:
    """Token para acesso cross-system (Proxy -> Secure Events)"""
    to_encode = {
        "sub": username,
        "type": "cross_system",
        "system": "secure_events",
        "iat": datetime.utcnow()
    }
    expire = datetime.utcnow() + timedelta(minutes=5)  # 5 min only
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def validate_cross_system_token(token: str) -> Optional[str]:
    """Valida token de cross-system e retorna username"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "cross_system":
            return None
        if payload.get("system") != "secure_events":
            return None
        return payload.get("sub")
    except JWTError:
        return None


def create_session_token(username: str) -> str:
    """Gera token de sessão válido por 3 horas"""
    token = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(64))
    SESSION_TOKENS[token] = {
        "username": username,
        "expires": datetime.utcnow() + timedelta(hours=3),
        "pages": {}
    }
    return token


def create_page_token(session_token: str, page: str) -> Optional[str]:
    """Gera token único por página (válido por 3 horas)"""
    session = SESSION_TOKENS.get(session_token)
    if not session:
        return None
    if session["expires"] < datetime.utcnow():
        del SESSION_TOKENS[session_token]
        return None
    
    # Gera token único para a página
    page_token = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(64))
    session["pages"][page] = {
        "token": page_token,
        "expires": datetime.utcnow() + timedelta(hours=3)
    }
    return page_token


def validate_page_token(session_token: str, page: str, page_token: str) -> bool:
    """Valida token de página"""
    session = SESSION_TOKENS.get(session_token)
    if not session:
        return False
    if session["expires"] < datetime.utcnow():
        return False
    
    page_data = session["pages"].get(page)
    if not page_data:
        return False
    if page_data["expires"] < datetime.utcnow():
        return False
    
    return page_data["token"] == page_token


def get_username_from_session(session_token: str) -> Optional[str]:
    """Retorna username do token de sessão"""
    session = SESSION_TOKENS.get(session_token)
    if not session:
        return None
    if session["expires"] < datetime.utcnow():
        return None
    return session["username"]


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        token_type: str = payload.get("type")
        
        if username is None:
            raise credentials_exception
        
        if token_type == "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
    except JWTError as e:
        logger.warning(f"JWT Error: {e}")
        raise credentials_exception
    
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )
    
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


class RequireRole:
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = allowed_roles
    
    def __call__(
        self,
        current_user: User = Depends(get_current_user)
    ):
        if not hasattr(current_user, 'role'):
            return current_user
        
        if current_user.role not in self.allowed_roles:
            logger.warning(f"User {current_user.username} denied access to role-restricted endpoint")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return current_user


def log_security_event(event_type: str, user: str, details: str, ip: str = None):
    logger.warning(
        f"SECURITY EVENT: {event_type} | User: {user} | IP: {ip} | Details: {details}"
    )


def verify_request_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    allowed_origins = ["http://localhost:3000", "http://localhost:8000", "http://127.0.0.1:8000"]
    return origin in allowed_origins if origin else True