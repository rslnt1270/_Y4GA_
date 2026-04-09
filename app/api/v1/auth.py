# © YAGA Project — Todos los derechos reservados
"""
api/v1/auth.py — Autenticación de conductores.

Tabla: usuarios (email, password_hash, nombre, roles…)
Cifrado: email_cifrado y phone_cifrado vía core.crypto (AES-256-GCM).
Respuesta: {token, conductor_id, nombre} — compatible con la PWA actual.
"""
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from jose import JWTError
import secrets
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from services.database import get_pool
from services.auth_service import hash_password, verify_password, create_token, decode_token
from core.crypto import encrypt_value
from core.limiter import limiter

router = APIRouter()

# ── Config email ──────────────────────────────────────────────────────────────
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
APP_URL   = os.getenv("APP_URL", "https://y4ga.app")

def _send_reset_email(to_email: str, nombre: str, token: str) -> bool:
    """Envía email de recuperación. Retorna False si SMTP no está configurado."""
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASS]):
        return False
    reset_url = f"{APP_URL}/yaga/?reset_token={token}"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Recupera tu contraseña — YAGA"
    msg["From"]    = f"YAGA App <{SMTP_USER}>"
    msg["To"]      = to_email
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:auto">
      <h2 style="color:#00ff88">Hola {nombre or 'conductor'} 👋</h2>
      <p>Recibimos una solicitud para restablecer tu contraseña en YAGA.</p>
      <a href="{reset_url}" style="display:inline-block;background:#00ff88;color:#0a0a0a;
         padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:bold;margin:16px 0">
        Restablecer contraseña
      </a>
      <p style="color:#888;font-size:.85rem">
        Este enlace expira en <strong>1 hora</strong>.<br>
        Si no solicitaste esto, ignora este mensaje.
      </p>
    </div>"""
    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_USER, to_email, msg.as_string())
        return True
    except Exception:
        return False


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
@limiter.limit("3/minute")
async def register(request: Request, body: RegistroBody, pool=Depends(get_pool)):
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
@limiter.limit("5/minute")
async def login(request: Request, body: LoginBody, pool=Depends(get_pool)):
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


# ── /auth/forgot-password ─────────────────────────────────────────────────────

class ForgotBody(BaseModel):
    email: str


@router.post("/auth/forgot-password")
@limiter.limit("3/hour")
async def forgot_password(request: Request, body: ForgotBody, pool=Depends(get_pool)):
    """Genera token de recuperación (Redis TTL 1h) y envía email si SMTP está configurado."""
    import redis.asyncio as aioredis
    email_norm = body.email.lower().strip()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, nombre FROM usuarios WHERE email = $1 AND deleted_at IS NULL",
            email_norm,
        )

    # Respuesta genérica siempre — no revelar si el email existe
    if not row:
        return {"message": "Si el email está registrado, recibirás instrucciones en breve."}

    reset_token = secrets.token_urlsafe(32)
    r = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
    try:
        await r.setex(f"reset:{reset_token}", 3600, str(row["id"]))
    finally:
        await r.aclose()

    email_sent = _send_reset_email(email_norm, row["nombre"] or "", reset_token)

    # Si no hay SMTP, exponer el token para uso admin/dev
    if not email_sent:
        reset_url = f"{APP_URL}/yaga/?reset_token={reset_token}"
        return {
            "message": "SMTP no configurado. Usa el enlace de administrador.",
            "reset_url": reset_url,
        }

    return {"message": "Si el email está registrado, recibirás instrucciones en breve."}


# ── /auth/reset-password ──────────────────────────────────────────────────────

class ResetBody(BaseModel):
    token: str
    nueva_password: str


@router.post("/auth/reset-password")
async def reset_password(body: ResetBody, pool=Depends(get_pool)):
    """Valida el token de Redis y actualiza la contraseña."""
    import redis.asyncio as aioredis

    if len(body.nueva_password) < 6:
        raise HTTPException(status_code=422, detail="La contraseña debe tener al menos 6 caracteres")

    r = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
    try:
        conductor_id = await r.get(f"reset:{body.token}")
        if not conductor_id:
            raise HTTPException(status_code=400, detail="Token inválido o expirado")
        conductor_id = conductor_id.decode()
        await r.delete(f"reset:{body.token}")  # token de un solo uso
    finally:
        await r.aclose()

    nuevo_hash = hash_password(body.nueva_password)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE usuarios SET password_hash = $1 WHERE id = $2 AND deleted_at IS NULL RETURNING id, nombre, email",
            nuevo_hash, conductor_id,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    token_jwt = create_token(str(row["id"]), row["email"])
    return {
        "message": "Contraseña actualizada correctamente",
        "token": token_jwt,
        "conductor_id": str(row["id"]),
        "nombre": row["nombre"],
    }
