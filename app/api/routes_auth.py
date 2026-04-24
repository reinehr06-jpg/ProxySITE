from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.core.database import get_db
from app.core.config import settings
from app.core.auth import (
    verify_password, get_password_hash, 
    create_access_token, create_refresh_token,
    get_current_user, log_security_event,
    create_session_token, get_username_from_session
)
from app.core.schemas import (
    UserCreate, UserLogin, TokenResponse, 
    HealthCheckResponse, ErrorResponse
)
from app.core.security import get_client_ip, limiter
from app.models.all_models import User
import logging
import random
import string
import secrets
import json
import pyotp
import qrcode
import io
import base64

logger = logging.getLogger(__name__)

CAPTCHA_STORE = {}  # {captcha_id: answer}

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/captcha")
async def get_captcha():
    """Generate simple math captcha"""
    import random
    
    # Generate random math problem
    a = random.randint(1, 10)
    b = random.randint(1, 10)
    op = random.choice(['+', '-', '*'])
    
    if op == '+':
        answer = a + b
    elif op == '-':
        answer = a - b
    else:
        answer = a * b
    
    # Create captcha token
    captcha_id = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
    CAPTCHA_STORE[captcha_id] = answer
    
    return {
        "captcha_id": captcha_id,
        "question": f"{a} {op} {b} = ?",
        "expires_in": 300
    }


@router.post("/login", response_model=TokenResponse)
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
    
    user = db.query(User).filter(User.username == form_data.username).first()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        log_security_event(
            "LOGIN_FAILED",
            form_data.username,
            "Invalid credentials",
            get_client_ip(request)
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        log_security_event(
            "LOGIN_FAILED",
            form_data.username,
            "Inactive account",
            get_client_ip(request)
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )
    
# Check if requires 2FA
    if getattr(user, 'otp_enabled', False) and getattr(user, 'otp_secret', None):
        # Generate temp token for 2FA step
        temp_token = create_access_token(data={
            "sub": user.username,
            "type": "2fa_pending",
            "temp": True
        })
        
        return {
            "require_verify_2fa": True,
            "temp_token": temp_token,
            "expires_in": 300
        }
    
    # 2FA not configured - need setup first
    if not getattr(user, 'otp_enabled', False):
        temp_token = create_access_token(data={
            "sub": user.username,
            "type": "2fa_pending",
            "temp": True
        })
        
        return {
            "require_2fa_setup": True,
            "temp_token": temp_token,
            "expires_in": 300
        }
    
    # No 2FA - normal login
    session_token = create_session_token(user.username)
    
    log_security_event(
        "LOGIN_SUCCESS",
        user.username,
        "User logged in successfully",
        get_client_ip(request)
    )
    
    return {
        "session_token": session_token,
        "expires_in": 10800
    }
    
    access_token = create_access_token(data={"sub": user.username})
    refresh_token = create_refresh_token(data={"sub": user.username})
    
    log_security_event(
        "LOGIN_SUCCESS",
        user.username,
        "User logged in successfully",
        get_client_ip(request)
    )
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/verify-2fa")
async def verify_2fa(
    request: Request,
    otp_code: str,
    db: Session = Depends(get_db)
):
    """Second step: verify TOTP code"""
    from fastapi import Header
    auth_header = request.headers.get("Authorization", "")
    temp_token = auth_header.replace("Bearer ", "")
    
    if not temp_token:
        raise HTTPException(status_code=401, detail="Temp token required")
    
    # Decode temp token
    try:
        payload = jwt.decode(temp_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "2fa_pending":
            raise HTTPException(status_code=401, detail="Invalid token type")
        username = payload.get("sub")
    except:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Verify OTP
    import pyotp
    otp_secret = user.otp_secret
    if not otp_secret:
        raise HTTPException(status_code=400, detail="2FA not configured")
    
    totp = pyotp.TOTP(otp_secret)
    if not totp.verify(otp_code, valid_window=1):
        raise HTTPException(status_code=401, detail="Invalid 2FA code")
    
    # Generate real tokens
    access_token = create_access_token(data={"sub": user.username})
    refresh_token = create_refresh_token(data={"sub": user.username})
    
    log_security_event(
        "LOGIN_2FA_SUCCESS",
        user.username,
        "2FA verified successfully",
        get_client_ip(request)
    )
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    access_token = create_access_token(data={"sub": current_user.username})
    refresh_token = create_refresh_token(data={"sub": current_user.username})
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    log_security_event(
        "LOGOUT",
        current_user.username,
        "User logged out",
        ""
    )
    return {"message": "Successfully logged out"}


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "is_active": current_user.is_active,
        "otp_enabled": getattr(current_user, 'otp_enabled', False),
        "otp_devices_count": len(eval(getattr(current_user, 'otp_devices', '[]'))) if hasattr(current_user, 'otp_devices') else 0
    }


@router.post("/setup-2fa")
async def setup_2fa(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Setup 2FA - generate new secret and QR code"""
    import pyotp
    import qrcode
    import io
    import base64
    import json
    
    # Generate new secret
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    
    # Generate provisioning URI
    provisioning_uri = totp.provisioning_uri(
        name=current_user.username,
        issuer_name='BasileiaProxy'
    )
    
    # Generate QR code as base64
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    qr_base64 = base64.b64encode(buffer.getvalue()).decode()
    
    # Store temporarily (not enabled until verified)
    current_user.otp_secret = secret
    db.commit()
    
    return {
        "secret": secret,
        "qr_code": f"data:image/png;base64,{qr_base64}",
        "provisioning_uri": provisioning_uri
    }


@router.post("/verify-2fa-setup")
async def verify_2fa_setup(
    request: Request,
    otp_code: str,
    device_name: str = "My Device",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Verify and enable 2FA"""
    import pyotp
    import json
    
    if not current_user.otp_secret:
        raise HTTPException(status_code=400, detail="Run setup-2fa first")
    
    totp = pyotp.TOTP(current_user.otp_secret)
    if not totp.verify(otp_code, valid_window=1):
        raise HTTPException(status_code=401, detail="Invalid code")
    
    # Get existing devices
    devices = json.loads(getattr(current_user, 'otp_devices', '[]'))
    
    # Add new device
    import uuid
    devices.append({
        "id": str(uuid.uuid4()),
        "name": device_name,
        "created_at": datetime.utcnow().isoformat()
    })
    
    current_user.otp_devices = json.dumps(devices)
    current_user.otp_enabled = True
    db.commit()
    
    return {"message": "2FA enabled successfully", "devices": devices}


@router.get("/2fa-devices")
async def list_2fa_devices(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all 2FA devices"""
    import json
    devices = json.loads(getattr(current_user, 'otp_devices', '[]'))
    return {"devices": devices}


@router.delete("/2fa-devices/{device_id}")
async def remove_2fa_device(
    device_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove a 2FA device"""
    import json
    devices = json.loads(getattr(current_user, 'otp_devices', '[]'))
    devices = [d for d in devices if d['id'] != device_id]
    current_user.otp_devices = json.dumps(devices)
    
    # Disable if no devices left
    if not devices:
        current_user.otp_enabled = False
        current_user.otp_secret = None
    
    db.commit()
    return {"message": "Device removed"}


@router.get("/cross-system-token")
async def generate_cross_system_token(current_user: User = Depends(get_current_user)):
    """Gera token para acessar Vault"""
    from app.core.auth import create_cross_system_token
    
    token = create_cross_system_token(current_user.username)
    
    return {
        "token": token,
        "url": f"/vault/?token={token}",
        "expires_in": 300
    }



@router.get("/health")
async def health_check():
    return {"status": "healthy"}