from datetime import datetime, timedelta
from jose import jwt
from core.config import settings

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    private_key = settings.get_jwt_private_key()
    encoded_jwt = jwt.encode(to_encode, private_key, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict):
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = data.copy()
    to_encode.update({"exp": expire, "type": "refresh"})
    private_key = settings.get_jwt_private_key()
    return jwt.encode(to_encode, private_key, algorithm=settings.JWT_ALGORITHM)

def verify_token(token: str):
    try:
        public_key = settings.get_jwt_public_key()
        payload = jwt.decode(token, public_key, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.JWTError:
        return None
