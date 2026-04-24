from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from pydantic import BaseModel, EmailStr
from app.core.database import get_db_secure as get_db
from app.core.config import settings
from app.core.events_security import (
    hash_password, verify_password, create_access_token,
    create_refresh_token, get_current_events_user, require_role,
    increment_failed_attempt, reset_failed_attempts, log_security_event
)
from app.models.events.events_user import EventsUser
import logging
import random
import string
import json

logger = logging.getLogger(__name__)

CAPTCHA_STORE = {}  # {captcha_id: answer}

router = APIRouter(prefix="/auth", tags=["Events Auth"])


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str = "events_operator"
    account_id: str = None


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str
    account_id: str = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.get("/captcha")
async def get_captcha():
    """Generate simple math captcha"""
    a = random.randint(1, 10)
    b = random.randint(1, 10)
    op = random.choice(['+', '-', '*'])
    
    if op == '+':
        answer = a + b
    elif op == '-':
        answer = a - b
    else:
        answer = a * b
    
    captcha_id = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
    CAPTCHA_STORE[captcha_id] = answer
    
    return {
        "captcha_id": captcha_id,
        "question": f"{a} {op} {b} = ?",
        "expires_in": 300
    }


@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    captcha_id: str = None,
    captcha_answer: str = None,
    db: Session = Depends(get_db)
):
    # Validate captcha if provided
    if captcha_id and captcha_answer:
        correct = CAPTCHA_STORE.get(captcha_id)
        if not correct or str(correct) != captcha_answer:
            raise HTTPException(status_code=400, detail="Captcha incorreto")
        del CAPTCHA_STORE[captcha_id]
    
    email = form_data.username
    password = form_data.password
    
    user = db.query(EventsUser).filter_by(email=email).first()
    
    if not user or not verify_password(password, user.password_hash):
        log_security_event(
            "LOGIN_FAILED",
            str(user.id) if user else "unknown",
            "Invalid credentials",
            get_client_ip(request)
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        log_security_event(
            "LOGIN_FAILED",
            str(user.id),
            "Inactive account",
            get_client_ip(request)
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )
    
    if user.locked_until and user.locked_until > datetime.utcnow():
        log_security_event(
            "LOGIN_FAILED",
            str(user.id),
            "Account locked",
            get_client_ip(request)
        )
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account temporarily locked. Try again later."
        )
    
    reset_failed_attempts(user, db)
    
    user.last_login = datetime.utcnow()
    db.commit()
    
    access_token = create_access_token(
        user_id=str(user.id),
        role=user.role,
        account_id=user.account_id
    )
    refresh_token = create_refresh_token(user_id=str(user.id))
    
    log_security_event(
        "LOGIN_SUCCESS",
        str(user.id),
        "User logged in successfully",
        get_client_ip(request)
    )
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.EVENTS_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role
        }
    )


@router.post("/refresh", response_model=LoginResponse)
async def refresh_token(
    request: Request,
    db: Session = Depends(get_db)
):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header"
        )
    
    refresh_token = auth_header.replace("Bearer ", "")
    
    from jose import jwt, JWTError
    from app.core.config import settings
    
    try:
        payload = jwt.decode(
            refresh_token,
            settings.EVENTS_JWT_SECRET,
            algorithms=["HS256"]
        )
        if payload.get("scope") != "secure_events_refresh":
            raise HTTPException(status_code=401, detail="Invalid token scope")
        user_id = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    user = db.query(EventsUser).filter_by(id=user_id, is_active=True).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    access_token = create_access_token(
        user_id=str(user.id),
        role=user.role,
        account_id=user.account_id
    )
    new_refresh_token = create_refresh_token(user_id=str(user.id))
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.EVENTS_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role
        }
    )


@router.post("/logout")
async def logout(
    request: Request,
    current_user: EventsUser = Depends(get_current_events_user)
):
    log_security_event(
        "LOGOUT",
        str(current_user.id),
        "User logged out",
        get_client_ip(request)
    )
    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: EventsUser = Depends(get_current_events_user)):
    return current_user


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(require_role("events_admin"))
):
    existing = db.query(EventsUser).filter_by(email=user_data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    user = EventsUser(
        name=user_data.name,
        email=user_data.email,
        password_hash=hash_password(user_data.password),
        role=user_data.role,
        account_id=user_data.account_id,
        is_active=True
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    log_security_event(
        "USER_CREATED",
        str(current_user.id),
        f"Created user: {user.id}",
        get_client_ip(request)
    )
    
    return user


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    request: Request,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(require_role("events_admin", "events_operator"))
):
    users = db.query(EventsUser).all()
    return users


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    request: Request,
    user_id: str,
    user_data: dict,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(require_role("events_admin"))
):
    user = db.query(EventsUser).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if "name" in user_data:
        user.name = user_data["name"]
    if "role" in user_data:
        user.role = user_data["role"]
    if "is_active" in user_data:
        user.is_active = user_data["is_active"]
    if "password" in user_data:
        user.password_hash = hash_password(user_data["password"])
    
    db.commit()
    db.refresh(user)
    
    log_security_event(
        "USER_UPDATED",
        str(current_user.id),
        f"Updated user: {user.id}",
        get_client_ip(request)
    )
    
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    request: Request,
    user_id: str,
    db: Session = Depends(get_db),
    current_user: EventsUser = Depends(require_role("events_admin"))
):
    user = db.query(EventsUser).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if str(user.id) == str(current_user.id):
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    
    db.delete(user)
    db.commit()
    
    log_security_event(
        "USER_DELETED",
        str(current_user.id),
        f"Deleted user: {user_id}",
        get_client_ip(request)
    )