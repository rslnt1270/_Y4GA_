# © YAGA Project — Todos los derechos reservados
"""
api/v1/auth.py — Autenticación de conductores.

Tabla: usuarios (email, password_hash, nombre, telefono, roles…)
Cifrado: email_cifrado y phone_cifrado vía core.crypto (AES-256-GCM).
Respuesta: {token, conductor_id, nombre} — compatible con la PWA actual.
"""
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from typing import Optional
from jose import JWTError

from services.database import get_pool
from services.auth_service import hash_password, verify_password, create_token, decode_token
from core.crypto import encrypt_value

router = APIRouter()


class RegistroBody(BaseModel):
    nombre: str
    email: str
    password: str
    telefono: Optional[str] = None


class LoginBody(BaseModel):
    email: str
    password: str


# ── /auth/me ─────────────────────────────────────────────────────────────────

@router.get("/auth/me")
async def me(
    authorization: Optional[str] = Header(None),
    pool=Depends(get_pool),
):
    """Valida el JWT y retorna datos del conductor autenticado."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token requerido")
    try:
        payload = decode_token(authorization[7:])
        conductor_id = payload["sub"]
    except (JWTError, KeyError, Exception):
        raise HTTPException(status_code=401, detail="Token inválido o expirado")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, nombre, email, deleted_at FROM usuarios WHERE id = $1",
            conductor_id,
        )
    if not row or row["deleted_at"] is not None:
        raise HTTPException(status_code=401, detail="Cuenta no encontrada")

    return {
        "conductor_id": str(row["id"]),
        "nombre": row["nombre"],
        "email": row["email"],
    }


# ── /auth/register ────────────────────────────────────────────────────────────

@router.post("/auth/register", status_code=201)
async def register(body: RegistroBody, pool=Depends(get_pool)):
    """
    Registra un nuevo conductor.
    email y phone se guardan en texto plano (lookup/unique) + cifrado AES-256.
    """
    if len(body.password) < 6:
        raise HTTPException(
            status_code=422, detail="La contraseña debe tener al menos 6 caracteres"
        )

    email_norm = body.email.lower().strip()

    async with pool.acquire() as conn:
        existe = await conn.fetchval(
            "SELECT id FROM usuarios WHERE email = $1 AND deleted_at IS NULL",
            email_norm,
        )
        if existe:
            raise HTTPException(status_code=400, detail="El email ya está registrado")

        email_cifrado = encrypt_value(email_norm)
        phone_cifrado = encrypt_value(body.telefono) if body.telefono else None

        conductor_id = await conn.fetchval(
            """
            INSERT INTO usuarios
                (nombre, email, email_cifrado, phone, phone_cifrado, password_hash, roles)
            VALUES ($1, $2, $3, $4, $5, $6, ARRAY['driver'])
            RETURNING id::text
            """,
            body.nombre.strip(),
            email_norm,
            email_cifrado,
            body.telefono,
            phone_cifrado,
            hash_password(body.password),
        )

    token = create_token(conductor_id, email_norm)
    return {
        "token": token,
        "conductor_id": conductor_id,
        "nombre": body.nombre.strip(),
    }


# ── /auth/login ───────────────────────────────────────────────────────────────

@router.post("/auth/login")
async def login(body: LoginBody, pool=Depends(get_pool)):
    """Login por email + contraseña. Devuelve JWT compatible con la PWA."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, nombre, password_hash
            FROM usuarios
            WHERE email = $1 AND deleted_at IS NULL
            """,
            body.email.lower().strip(),
        )

    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    token = create_token(str(row["id"]), body.email.lower().strip())
    return {
        "token": token,
        "conductor_id": str(row["id"]),
        "nombre": row["nombre"],
    }
