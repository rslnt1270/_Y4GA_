from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert
from sqlalchemy import func
from pydantic import BaseModel
import os

from db import get_db
from models.usuario import Usuario
from models.auditoria import Auditoria
from core.security import get_password_hash, verify_password
from core.auth import create_access_token, create_refresh_token, verify_token
from core.redis import redis_client
from core.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# --- Schemas ---
class UserCreate(BaseModel):
    email: str
    password: str
    phone: str = None

class UserLogin(BaseModel):
    email: str
    password: str

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshRequest(BaseModel):
    refresh_token: str

class LogoutRequest(BaseModel):
    refresh_token: str

# --- Endpoints ---
@router.post("/register", response_model=Token)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db), request: Request = None):
    # Verificar si email ya existe
    result = await db.execute(select(Usuario).where(Usuario.email == user_data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Cifrar email y phone con pgcrypto
    encrypted_email = func.pgp_sym_encrypt(user_data.email, os.getenv("DB_ENCRYPT_KEY"))
    encrypted_phone = func.pgp_sym_encrypt(user_data.phone, os.getenv("DB_ENCRYPT_KEY")) if user_data.phone else None
    
    new_user = Usuario(
        email=user_data.email,
        email_cifrado=encrypted_email,
        phone=user_data.phone,
        phone_cifrado=encrypted_phone,
        password_hash=get_password_hash(user_data.password),
        roles=["driver"]
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    
    # Generar tokens
    access_token = create_access_token(data={"sub": str(new_user.id), "roles": new_user.roles})
    refresh_token = create_refresh_token(data={"sub": str(new_user.id)})
    
    # Guardar refresh token en Redis
    await redis_client.setex(f"refresh:{new_user.id}", settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400, refresh_token)
    
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}

@router.post("/login", response_model=Token)
async def login(user_data: UserLogin, db: AsyncSession = Depends(get_db), request: Request = None):
    result = await db.execute(select(Usuario).where(Usuario.email == user_data.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(user_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access_token = create_access_token(data={"sub": str(user.id), "roles": user.roles})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})
    
    # Guardar refresh token en Redis (sobrescribe cualquier anterior)
    await redis_client.setex(f"refresh:{user.id}", settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400, refresh_token)
    
    # Registrar login en auditoría
    await db.execute(
        insert(Auditoria).values(
            usuario_id=user.id,
            accion="login",
            ip=request.client.host if request else None,
            user_agent=request.headers.get("user-agent") if request else None
        )
    )
    await db.commit()
    
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}

@router.post("/refresh")
async def refresh(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = verify_token(data.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    user_id = payload.get("sub")
    
    # Verificar que el refresh token esté en Redis y coincida
    stored_refresh = await redis_client.get(f"refresh:{user_id}")
    if not stored_refresh or stored_refresh != data.refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token invalid or revoked")
    
    # Generar nuevo access token
    access_token = create_access_token(data={"sub": user_id, "roles": payload.get("roles", ["driver"])})
    return {"access_token": access_token}

@router.post("/logout")
async def logout(data: LogoutRequest, token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db), request: Request = None):
    # Verificar el access token para obtener user_id (opcional, también podemos extraer del refresh)
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid access token")
    
    user_id = payload.get("sub")
    
    # Verificar que el refresh token enviado coincida con el almacenado
    stored_refresh = await redis_client.get(f"refresh:{user_id}")
    if not stored_refresh or stored_refresh != data.refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token mismatch")
    
    # Eliminar el refresh token de Redis
    await redis_client.delete(f"refresh:{user_id}")
    
    # Registrar logout en auditoría
    await db.execute(
        insert(Auditoria).values(
            usuario_id=user_id,
            accion="logout",
            ip=request.client.host if request else None,
            user_agent=request.headers.get("user-agent") if request else None
        )
    )
    await db.commit()
    
    return {"msg": "Logged out"}
