# © YAGA Project
"""
YAGA PROJECT - Servicio de Autenticacion
"""
import bcrypt
from jose import jwt
from datetime import datetime, timedelta
import os
import secrets as _secrets

_raw_secret = os.getenv("JWT_SECRET", "")
if not _raw_secret or len(_raw_secret) < 32:
    import logging
    logging.getLogger("yaga.auth").critical(
        "JWT_SECRET no configurada o demasiado corta (<32 chars). "
        "Usando secret de sesión efímero — todos los tokens se invalidarán al reiniciar."
    )
    _raw_secret = _secrets.token_hex(32)
SECRET_KEY = _raw_secret
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 dias (login/register — compat PWA actual)
ACCESS_TOKEN_EXPIRE_MINUTES_AFTER_REFRESH = 15  # Sprint 10: post-refresh más corto


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_token(conductor_id: str, email: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": conductor_id, "email": email, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_token_after_refresh(conductor_id: str, email: str) -> str:
    """Access token corto (15 min) emitido por /auth/refresh. Payload idéntico a create_token."""
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES_AFTER_REFRESH)
    payload = {"sub": conductor_id, "email": email, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
