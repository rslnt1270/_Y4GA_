"""
YAGA PROJECT - Endpoints de Autenticación
"""
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
from jose import JWTError
from services.database import get_pool
from services.auth_service import hash_password, verify_password, create_token, decode_token

router = APIRouter()


class RegistroBody(BaseModel):
    nombre: str
    email: str
    password: str
    telefono: Optional[str] = None


class LoginBody(BaseModel):
    email: str
    password: str


@router.get("/auth/me")
async def me(authorization: Optional[str] = Header(None), pool=Depends(get_pool)):
    """Valida el JWT y retorna datos del conductor autenticado."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token requerido")
    try:
        payload = decode_token(authorization[7:])
        conductor_id = payload["sub"]
    except (JWTError, KeyError):
        raise HTTPException(status_code=401, detail="Token invalido o expirado")

    async with pool.acquire() as conn:
        conductor = await conn.fetchrow(
            "SELECT id, nombre, email, activo FROM conductores WHERE id = $1",
            conductor_id
        )
    if not conductor or not conductor["activo"]:
        raise HTTPException(status_code=401, detail="Cuenta no encontrada o desactivada")

    return {
        "conductor_id": str(conductor["id"]),
        "nombre": conductor["nombre"],
        "email": conductor["email"],
    }


@router.post("/auth/register", status_code=201)
async def register(body: RegistroBody, pool=Depends(get_pool)):
    async with pool.acquire() as conn:
        existe = await conn.fetchval(
            "SELECT id FROM conductores WHERE email = $1", body.email
        )
        if existe:
            raise HTTPException(status_code=400, detail="El email ya está registrado")

        conductor_id = await conn.fetchval(
            """INSERT INTO conductores (nombre, email, password_hash, telefono)
               VALUES ($1, $2, $3, $4) RETURNING id::text""",
            body.nombre, body.email, hash_password(body.password), body.telefono
        )

        token = create_token(conductor_id, body.email)
        return {"token": token, "conductor_id": conductor_id, "nombre": body.nombre}


@router.post("/auth/login")
async def login(body: LoginBody, pool=Depends(get_pool)):
    async with pool.acquire() as conn:
        conductor = await conn.fetchrow(
            "SELECT id, nombre, password_hash, activo FROM conductores WHERE email = $1",
            body.email
        )
        if not conductor or not verify_password(body.password, conductor["password_hash"]):
            raise HTTPException(status_code=401, detail="Credenciales incorrectas")

        if not conductor["activo"]:
            raise HTTPException(status_code=403, detail="Cuenta desactivada")

        token = create_token(str(conductor["id"]), body.email)
        return {"token": token, "conductor_id": str(conductor["id"]), "nombre": conductor["nombre"]}
