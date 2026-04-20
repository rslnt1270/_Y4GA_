# © YAGA Project — Todos los derechos reservados
"""
api/v1/auth.py — Autenticación de conductores.

Tabla: usuarios (email, password_hash, nombre, roles…)
Cifrado: email_cifrado y phone_cifrado vía core.crypto (AES-256-GCM).
Respuesta: {token, conductor_id, nombre} — compatible con la PWA actual.
"""
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel
from typing import Optional
from jose import JWTError
import asyncio
import secrets
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from services.database import get_pool
from services.auth_service import (
    hash_password,
    verify_password,
    create_token,
    create_token_after_refresh,
    decode_token,
)
from services.audit_service import log_action
from services.refresh_service import (
    RefreshTokenError,
    ReuseDetected,
    create_refresh_token,
    revoke_all_families_for_user,
    revoke_token,
    validate_and_rotate,
)
from core.cookies import (
    clear_refresh_cookie,
    get_refresh_cookie,
    set_refresh_cookie,
    validate_origin,
)
from core.crypto import encrypt_value
from core.limiter import limiter
from core.rate_limiter import check_user_rate_limit, reset_user_rate_limit
from core.redis import redis_client


def _client_ip(request: Request) -> str:
    """Obtiene la IP real del cliente respetando X-Forwarded-For."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


def _client_ua(request: Request) -> str:
    """Obtiene el User-Agent del cliente."""
    return request.headers.get("user-agent", "")

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
async def register(
    request: Request,
    body: RegistroBody,
    response: Response,
    pool=Depends(get_pool),
):
    """
    Registra un nuevo conductor.
    email y phone se guardan en texto plano (lookup/unique) + cifrado AES-256.
    """
    if len(body.password) < 6:
        raise HTTPException(
            status_code=422, detail="La contraseña debe tener al menos 6 caracteres"
        )

    email_norm = body.email.lower().strip()
    ip = _client_ip(request)
    ua = _client_ua(request)

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

    # Refresh token cookie (sliding 30d, cap 60d)
    emission = await create_refresh_token(conductor_id, ip, ua)
    set_refresh_cookie(response, emission.token_id, emission.ttl_cookie_seconds)

    asyncio.create_task(log_action(
        usuario_id=conductor_id,
        accion="registro",
        ip=ip,
        user_agent=ua,
        detalles={"email": email_norm, "familia_id": emission.familia_id},
    ))

    return {
        "token": token,
        "conductor_id": conductor_id,
        "nombre": body.nombre.strip(),
    }


# ── /auth/login ───────────────────────────────────────────────────────────────

@router.post("/auth/login")
@limiter.limit("5/minute")
async def login(
    request: Request,
    body: LoginBody,
    response: Response,
    pool=Depends(get_pool),
):
    """Login por email + contraseña. Devuelve JWT compatible con la PWA."""
    email_norm = body.email.lower().strip()
    ip = _client_ip(request)
    ua = _client_ua(request)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, nombre, password_hash
            FROM usuarios
            WHERE email = $1 AND deleted_at IS NULL
            """,
            email_norm,
        )

    if row:
        await check_user_rate_limit(
            str(row["id"]),
            action="login",
            max_attempts=5,
            window_seconds=900,
        )

    if not row or not verify_password(body.password, row["password_hash"]):
        asyncio.create_task(log_action(
            usuario_id=str(row["id"]) if row else None,
            accion="login_fallido",
            ip=ip,
            user_agent=ua,
            detalles={"email": email_norm},
        ))
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    await reset_user_rate_limit(str(row["id"]), "login")
    conductor_id = str(row["id"])
    token = create_token(conductor_id, email_norm)

    # Refresh token cookie (sliding 30d, cap 60d)
    emission = await create_refresh_token(conductor_id, ip, ua)
    set_refresh_cookie(response, emission.token_id, emission.ttl_cookie_seconds)

    asyncio.create_task(log_action(
        usuario_id=conductor_id,
        accion="login_exitoso",
        ip=ip,
        user_agent=ua,
        detalles={"email": email_norm, "familia_id": emission.familia_id},
    ))

    return {
        "token": token,
        "conductor_id": conductor_id,
        "nombre": row["nombre"],
    }


# ── /auth/forgot-password ─────────────────────────────────────────────────────

class ForgotBody(BaseModel):
    email: str


@router.post("/auth/forgot-password")
@limiter.limit("3/hour")
async def forgot_password(request: Request, body: ForgotBody, pool=Depends(get_pool)):
    """Genera token de recuperación (Redis TTL 1h) y envía email si SMTP está configurado."""
    email_norm = body.email.lower().strip()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, nombre FROM usuarios WHERE email = $1 AND deleted_at IS NULL",
            email_norm,
        )

    # Respuesta genérica siempre — no revelar si el email existe
    if not row:
        asyncio.create_task(log_action(
            usuario_id=None,
            accion="reset_password_solicitado",
            ip=_client_ip(request),
            user_agent=_client_ua(request),
            detalles={"email": email_norm, "encontrado": False},
        ))
        return {"message": "Si el email está registrado, recibirás instrucciones en breve."}

    asyncio.create_task(log_action(
        usuario_id=str(row["id"]),
        accion="reset_password_solicitado",
        ip=_client_ip(request),
        user_agent=_client_ua(request),
        detalles={"email": email_norm, "encontrado": True},
    ))

    reset_token = secrets.token_urlsafe(32)
    await redis_client.setex(f"reset:{reset_token}", 3600, str(row["id"]))

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
async def reset_password(
    request: Request,
    body: ResetBody,
    response: Response,
    pool=Depends(get_pool),
):
    """Valida el token de Redis y actualiza la contraseña."""
    if len(body.nueva_password) < 6:
        raise HTTPException(status_code=422, detail="La contraseña debe tener al menos 6 caracteres")

    conductor_id = await redis_client.get(f"reset:{body.token}")
    if not conductor_id:
        raise HTTPException(status_code=400, detail="Token inválido o expirado")
    await redis_client.delete(f"reset:{body.token}")  # token de un solo uso

    nuevo_hash = hash_password(body.nueva_password)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE usuarios SET password_hash = $1 WHERE id = $2 AND deleted_at IS NULL RETURNING id, nombre, email",
            nuevo_hash, conductor_id,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    uid = str(row["id"])
    ip = _client_ip(request)
    ua = _client_ua(request)

    # Revocar TODAS las sesiones anteriores (cambio de credenciales)
    familias_revocadas = await revoke_all_families_for_user(
        uid, motivo="password_reset"
    )

    token_jwt = create_token(uid, row["email"])

    # Nueva familia de refresh para esta sesión
    emission = await create_refresh_token(uid, ip, ua)
    set_refresh_cookie(response, emission.token_id, emission.ttl_cookie_seconds)

    asyncio.create_task(log_action(
        usuario_id=uid,
        accion="reset_password_completado",
        ip=ip,
        user_agent=ua,
        detalles={
            "email": row["email"],
            "familias_revocadas": familias_revocadas,
            "familia_id": emission.familia_id,
        },
    ))

    return {
        "message": "Contraseña actualizada correctamente",
        "token": token_jwt,
        "conductor_id": uid,
        "nombre": row["nombre"],
    }


# ── /auth/refresh ─────────────────────────────────────────────────────────────

@router.post("/auth/refresh")
@limiter.limit("60/minute")
async def refresh(request: Request, response: Response, pool=Depends(get_pool)):
    """
    Rota el refresh token y emite un access token corto (15 min).
    Fallos genéricos: 401 sin exponer la razón. Incluye detección de reuse.
    """
    if not validate_origin(request):
        # Origin inválido → defensa en profundidad contra CSRF
        raise HTTPException(status_code=401, detail="No autorizado")

    token_id = get_refresh_cookie(request)
    if not token_id:
        raise HTTPException(status_code=401, detail="No autorizado")

    ip = _client_ip(request)
    ua = _client_ua(request)

    try:
        emission = await validate_and_rotate(token_id, ip, ua)
    except ReuseDetected:
        # Limpiar cookie atacada y auditar — luego 401 genérico
        clear_refresh_cookie(response)
        asyncio.create_task(log_action(
            usuario_id=None,
            accion="auth_reuse_detected",
            ip=ip,
            user_agent=ua,
            detalles={"offending_token_prefix": token_id[:8]},
        ))
        raise HTTPException(status_code=401, detail="No autorizado")
    except RefreshTokenError:
        clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="No autorizado")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, nombre FROM usuarios WHERE id = $1 AND deleted_at IS NULL",
            emission.usuario_id,
        )

    if not row:
        # Usuario borrado entre login y refresh → revocar todo y rechazar
        await revoke_all_families_for_user(emission.usuario_id, motivo="usuario_eliminado")
        clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="No autorizado")

    access = create_token_after_refresh(str(row["id"]), row["email"])
    set_refresh_cookie(response, emission.token_id, emission.ttl_cookie_seconds)

    asyncio.create_task(log_action(
        usuario_id=str(row["id"]),
        accion="auth_refresh",
        ip=ip,
        user_agent=ua,
        detalles={
            "familia_id": emission.familia_id,
            "nuevo_token_prefix": emission.token_id[:8],
        },
    ))

    return {
        "token": access,
        "conductor_id": str(row["id"]),
        "nombre": row["nombre"],
    }


# ── /auth/logout ──────────────────────────────────────────────────────────────

@router.post("/auth/logout", status_code=204)
async def logout(request: Request, response: Response):
    """
    Cierra la sesión actual (revoca el refresh token). Idempotente:
    sin cookie responde 204 igual (no revela estado al atacante).
    """
    token_id = get_refresh_cookie(request)
    clear_refresh_cookie(response)

    if not token_id:
        return Response(status_code=204)

    ip = _client_ip(request)
    ua = _client_ua(request)

    usuario_id = await revoke_token(token_id)

    asyncio.create_task(log_action(
        usuario_id=usuario_id,
        accion="auth_logout",
        ip=ip,
        user_agent=ua,
        detalles={"token_prefix": token_id[:8]},
    ))
    return Response(status_code=204)
