import os
import base64
import hmac
import hashlib
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import load_pem_public_key, load_pem_private_key, Encoding, PublicFormat, PrivateFormat, NoEncryption
from cryptography.hazmat.backends import default_backend
from datetime import datetime, timedelta
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)

SECURE_MASTER_KEY = os.environ.get("SECURE_MASTER_KEY", "")
SECURE_WEBHOOK_SECRET = os.environ.get("SECURE_WEBHOOK_SECRET", "")
QR_HMAC_SECRET = os.environ.get("QR_HMAC_SECRET", "")


class CryptoService:
    _fernet: Optional[Fernet] = None
    
    @classmethod
    def get_fernet(cls) -> Fernet:
        if cls._fernet is None:
            if not SECURE_MASTER_KEY:
                raise ValueError("SECURE_MASTER_KEY not configured")
            cls._fernet = Fernet(SECURE_MASTER_KEY.encode())
        return cls._fernet
    
    @classmethod
    def encrypt(cls, data: str) -> str:
        fernet = cls.get_fernet()
        encrypted = fernet.encrypt(data.encode())
        return base64.urlsafe_b64encode(encrypted).decode()
    
    @classmethod
    def decrypt(cls, encrypted_data: str) -> str:
        fernet = cls.get_fernet()
        decrypted = fernet.decrypt(base64.urlsafe_b64decode(encrypted_data.encode()))
        return decrypted.decode()
    
    @classmethod
    def encrypt_bytes(cls, data: bytes) -> bytes:
        fernet = cls.get_fernet()
        return fernet.encrypt(data)
    
    @classmethod
    def decrypt_bytes(cls, encrypted_data: bytes) -> bytes:
        fernet = cls.get_fernet()
        return fernet.decrypt(encrypted_data)
    
    @classmethod
    def generate_rsa_keypair(cls) -> Tuple[str, str]:
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        private_pem = private_key.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.PKCS8,
            encryption_algorithm=NoEncryption()
        ).decode()
        
        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=Encoding.PEM,
            format=PublicFormat.SubjectPublicKeyInfo
        ).decode()
        
        return private_pem, public_pem
    
    @classmethod
    def encrypt_private_key(cls, private_pem: str) -> str:
        fernet = cls.get_fernet()
        encrypted = fernet.encrypt(private_pem.encode())
        return base64.urlsafe_b64encode(encrypted).decode()
    
    @classmethod
    def decrypt_private_key(cls, encrypted_private_pem: str) -> str:
        fernet = cls.get_fernet()
        decrypted = fernet.decrypt(base64.urlsafe_b64decode(encrypted_private_pem.encode()))
        return decrypted.decode()
    
    @classmethod
    def sign_hmac(cls, payload: dict, secret: str = None) -> str:
        if secret is None:
            secret = SECURE_WEBHOOK_SECRET
        
        if not secret:
            raise ValueError("SECURE_WEBHOOK_SECRET not configured")
        
        import json
        message = json.dumps(payload, sort_keys=True)
        
        signature = hmac.new(
            secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return f"sha256={signature}"
    
    @classmethod
    def verify_hmac(cls, payload: dict, signature: str, secret: str = None) -> bool:
        if signature is None:
            return False
        
        if signature.startswith("sha256="):
            signature = signature[7:]
        
        if secret is None:
            secret = SECURE_WEBHOOK_SECRET
        
        if not secret:
            raise ValueError("SECURE_WEBHOOK_SECRET not configured")
        
        import json
        message = json.dumps(payload, sort_keys=True)
        
        expected = hmac.new(
            secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected)
    
    @classmethod
    def sign_qr_hmac(cls, qr_payload: dict) -> str:
        if not QR_HMAC_SECRET:
            raise ValueError("QR_HMAC_SECRET not configured")
        
        import json
        message = json.dumps(qr_payload, sort_keys=True)
        
        signature = hmac.new(
            QR_HMAC_SECRET.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return signature
    
    @classmethod
    def verify_qr_hmac(cls, qr_payload: dict, signature: str) -> bool:
        if not QR_HMAC_SECRET or not signature:
            return False
        
        import json
        message = json.dumps(qr_payload, sort_keys=True)
        
        expected = hmac.new(
            QR_HMAC_SECRET.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected)
    
    @classmethod
    def create_qr_token(cls, ticket_id: str, event_id: str, expires_at: datetime = None) -> str:
        import json
        import base64
        
        if expires_at is None:
            expires_at = datetime.utcnow() + timedelta(hours=24)
        
        payload = {
            "ticket_id": ticket_id,
            "event_id": event_id,
            "exp": expires_at.isoformat()
        }
        
        qr_payload = {
            "data": payload,
            "signature": cls.sign_qr_hmac(payload)
        }
        
        token = base64.b64encode(json.dumps(qr_payload).encode()).decode()
        return token
    
    @classmethod
    def verify_qr_token(cls, token: str) -> Optional[dict]:
        import json
        import base64
        
        try:
            qr_data = json.loads(base64.b64decode(token).decode())
        except Exception:
            return None
        
        data = qr_data.get("data", {})
        signature = qr_data.get("signature", "")
        
        if not cls.verify_qr_hmac(data, signature):
            return None
        
        exp = data.get("exp")
        if exp:
            expiry = datetime.fromisoformat(exp.replace("Z", "+00:00"))
            if datetime.utcnow() > expiry.replace(tzinfo=None):
                return None
        
        return data


def encrypt_data(data: str) -> str:
    return CryptoService.encrypt(data)


def decrypt_data(encrypted_data: str) -> str:
    return CryptoService.decrypt(encrypted_data)


def generate_keypair() -> Tuple[str, str]:
    return CryptoService.generate_rsa_keypair()


def encrypt_private_key(private_pem: str) -> str:
    return CryptoService.encrypt_private_key(private_pem)


def decrypt_private_key(encrypted_private_pem: str) -> str:
    return CryptoService.decrypt_private_key(encrypted_private_pem)


def sign_webhook(payload: dict) -> str:
    return CryptoService.sign_hmac(payload)


def verify_webhook(payload: dict, signature: str) -> bool:
    return CryptoService.verify_hmac(payload, signature)


def create_qr_token(ticket_id: str, event_id: str, expires_at: datetime = None) -> str:
    return CryptoService.create_qr_token(ticket_id, event_id, expires_at)


def verify_qr_token(token: str) -> Optional[dict]:
    return CryptoService.verify_qr_token(token)