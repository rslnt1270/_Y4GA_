from datetime import datetime, timedelta
from jose import jwt, JWTError

PRIVATE_KEY_PATH = "certs/private_key.pem"
PUBLIC_KEY_PATH = "certs/public_key.pem"
ALGORITHM = "RS256"

def _load_key(file_path: str) -> str:
    with open(file_path, 'r') as f: return f.read()

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    to_encode.update({"exp": datetime.utcnow() + timedelta(minutes=30)})
    return jwt.encode(to_encode, _load_key(PRIVATE_KEY_PATH), algorithm=ALGORITHM)

def verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, _load_key(PUBLIC_KEY_PATH), algorithms=[ALGORITHM])
    except JWTError:
        return None
