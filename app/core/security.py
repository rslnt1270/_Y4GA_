import bcrypt
import hashlib

def get_password_hash(password: str) -> str:
    # Pre-hash con SHA-256 para evitar límite de 72 bytes de bcrypt
    hashed = hashlib.sha256(password.encode('utf-8')).hexdigest()
    # bcrypt requiere bytes
    return bcrypt.hashpw(hashed.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    hashed = hashlib.sha256(plain_password.encode('utf-8')).hexdigest()
    return bcrypt.checkpw(hashed.encode('utf-8'), hashed_password.encode('utf-8'))
