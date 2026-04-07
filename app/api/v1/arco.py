# © YAGA Project — Todos los derechos reservados
"""
api/v1/arco.py — Endpoints ARCO (Acceso, Rectificacion, Cancelacion, Oposicion).

Cumplimiento LFPDPPP para conductores YAGA.
Cada operacion se registra en la tabla auditoria.
Usa validacion JWT inline (Sistema A HS256) y asyncpg directo.
"""
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from jose import JWTError
import json

from services.database import get_pool
from services.auth_service import decode_token
from core.crypto import encrypt_value, decrypt_value

router = APIRouter()


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_conductor_id(authorization: Optional[str]) -> str:
    """Extrae conductor_id del JWT (patron inline de auth.py)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token requerido")
    try:
        payload = decode_token(authorization[7:])
        return payload["sub"]
    except (JWTError, KeyError, Exception):
        raise HTTPException(status_code=401, detail="Token invalido o expirado")


async def _registrar_auditoria(
    conn, usuario_id: str, accion: str, detalles: dict,
    ip: Optional[str], user_agent: Optional[str]
) -> None:
    """Inserta registro en tabla auditoria."""
    await conn.execute(
        """INSERT INTO auditoria (usuario_id, accion, detalles, ip, user_agent)
           VALUES ($1, $2, $3::jsonb, $4, $5)""",
        usuario_id, accion, json.dumps(detalles), ip, user_agent,
    )


# ── Schemas ──────────────────────────────────────────────────────────────────

class RectificacionBody(BaseModel):
    email: Optional[str] = None
    telefono: Optional[str] = None


class OposicionBody(BaseModel):
    finalidad: str  # "marketing" | "investigacion"
    activo: bool


# ── GET /acceso ──────────────────────────────────────────────────────────────

@router.get("/acceso")
async def arco_acceso(
    request: Request,
    authorization: Optional[str] = Header(None),
    pool=Depends(get_pool),
):
    """Derecho de Acceso LFPDPPP: retorna datos personales del conductor."""
    conductor_id = await _get_conductor_id(authorization)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT id, nombre, email, phone, email_cifrado, phone_cifrado,
                      created_at, deleted_at
               FROM usuarios WHERE id = $1""",
            conductor_id,
        )
        if not row or row["deleted_at"] is not None:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        # Descifrar datos si existen columnas cifradas
        email_descifrado = None
        phone_descifrado = None
        if row["email_cifrado"]:
            try:
                email_descifrado = decrypt_value(row["email_cifrado"])
            except Exception:
                email_descifrado = row["email"]
        if row["phone_cifrado"]:
            try:
                phone_descifrado = decrypt_value(row["phone_cifrado"])
            except Exception:
                phone_descifrado = row["phone"]

        # Consentimientos del usuario
        consentimientos = await conn.fetch(
            """SELECT finalidad, estado, es_obligatorio, fecha_otorgamiento, fecha_revocacion
               FROM consentimientos WHERE usuario_id = $1""",
            conductor_id,
        )

        await _registrar_auditoria(
            conn, conductor_id, "arco_acceso",
            {"campos_entregados": ["nombre", "email", "phone", "consentimientos"]},
            request.client.host if request.client else None,
            request.headers.get("user-agent"),
        )

    return {
        "conductor_id": str(row["id"]),
        "nombre": row["nombre"],
        "email": email_descifrado or row["email"],
        "telefono": phone_descifrado or row["phone"],
        "created_at": str(row["created_at"]) if row["created_at"] else None,
        "consentimientos": [
            {
                "finalidad": c["finalidad"],
                "estado": c["estado"],
                "es_obligatorio": c["es_obligatorio"],
                "fecha_otorgamiento": str(c["fecha_otorgamiento"]) if c["fecha_otorgamiento"] else None,
                "fecha_revocacion": str(c["fecha_revocacion"]) if c["fecha_revocacion"] else None,
            }
            for c in consentimientos
        ],
    }


# ── PUT /rectificacion ──────────────────────────────────────────────────────

@router.put("/rectificacion")
async def arco_rectificacion(
    body: RectificacionBody,
    request: Request,
    authorization: Optional[str] = Header(None),
    pool=Depends(get_pool),
):
    """Derecho de Rectificacion LFPDPPP: actualiza email y/o telefono."""
    conductor_id = await _get_conductor_id(authorization)

    if not body.email and not body.telefono:
        raise HTTPException(status_code=400, detail="Debe enviar al menos email o telefono")

    async with pool.acquire() as conn:
        # Verificar que el usuario existe
        existe = await conn.fetchval(
            "SELECT id FROM usuarios WHERE id = $1 AND deleted_at IS NULL",
            conductor_id,
        )
        if not existe:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        campos_actualizados = []

        if body.email:
            email_norm = body.email.lower().strip()
            # Validar unicidad
            conflicto = await conn.fetchval(
                "SELECT id FROM usuarios WHERE email = $1 AND id != $2 AND deleted_at IS NULL",
                email_norm, conductor_id,
            )
            if conflicto:
                raise HTTPException(status_code=409, detail="El email ya esta registrado por otro usuario")

            email_cifrado = encrypt_value(email_norm)
            await conn.execute(
                "UPDATE usuarios SET email = $1, email_cifrado = $2 WHERE id = $3",
                email_norm, email_cifrado, conductor_id,
            )
            campos_actualizados.append("email")

        if body.telefono:
            telefono_norm = body.telefono.strip()
            # Validar unicidad de telefono si existe columna phone
            conflicto_phone = await conn.fetchval(
                "SELECT id FROM usuarios WHERE phone = $1 AND id != $2 AND deleted_at IS NULL",
                telefono_norm, conductor_id,
            )
            if conflicto_phone:
                raise HTTPException(status_code=409, detail="El telefono ya esta registrado por otro usuario")

            phone_cifrado = encrypt_value(telefono_norm)
            await conn.execute(
                "UPDATE usuarios SET phone = $1, phone_cifrado = $2 WHERE id = $3",
                telefono_norm, phone_cifrado, conductor_id,
            )
            campos_actualizados.append("telefono")

        await _registrar_auditoria(
            conn, conductor_id, "arco_rectificacion",
            {"campos_actualizados": campos_actualizados},
            request.client.host if request.client else None,
            request.headers.get("user-agent"),
        )

    return {"message": "Datos actualizados correctamente", "campos": campos_actualizados}


# ── POST /cancelacion ───────────────────────────────────────────────────────

@router.post("/cancelacion")
async def arco_cancelacion(
    request: Request,
    authorization: Optional[str] = Header(None),
    pool=Depends(get_pool),
):
    """Derecho de Cancelacion LFPDPPP: soft-delete y anonimizacion de PII."""
    conductor_id = await _get_conductor_id(authorization)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email FROM usuarios WHERE id = $1 AND deleted_at IS NULL",
            conductor_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Usuario no encontrado o ya cancelado")

        # Soft delete + anonimizar PII
        await conn.execute(
            """UPDATE usuarios
               SET deleted_at = NOW(),
                   email = '[CANCELADO]',
                   email_cifrado = NULL,
                   phone = '[CANCELADO]',
                   phone_cifrado = NULL
               WHERE id = $1""",
            conductor_id,
        )

        await _registrar_auditoria(
            conn, conductor_id, "arco_cancelacion",
            {"accion": "soft_delete_y_anonimizacion"},
            request.client.host if request.client else None,
            request.headers.get("user-agent"),
        )

    return {"message": "Cuenta cancelada. Tus datos personales han sido anonimizados."}


# ── POST /oposicion ─────────────────────────────────────────────────────────

@router.post("/oposicion")
async def arco_oposicion(
    body: OposicionBody,
    request: Request,
    authorization: Optional[str] = Header(None),
    pool=Depends(get_pool),
):
    """Derecho de Oposicion LFPDPPP: toggle finalidad secundaria."""
    conductor_id = await _get_conductor_id(authorization)

    # Solo finalidades secundarias son revocables
    if body.finalidad not in ("marketing", "investigacion"):
        raise HTTPException(
            status_code=400,
            detail="Solo se puede ejercer oposicion sobre finalidades secundarias: marketing, investigacion",
        )

    async with pool.acquire() as conn:
        # Verificar que el usuario existe
        existe = await conn.fetchval(
            "SELECT id FROM usuarios WHERE id = $1 AND deleted_at IS NULL",
            conductor_id,
        )
        if not existe:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        # Upsert en consentimientos
        existing = await conn.fetchrow(
            "SELECT id, estado FROM consentimientos WHERE usuario_id = $1 AND finalidad = $2",
            conductor_id, body.finalidad,
        )

        if existing:
            if body.activo:
                await conn.execute(
                    """UPDATE consentimientos
                       SET estado = true, fecha_otorgamiento = NOW(), fecha_revocacion = NULL
                       WHERE id = $1""",
                    existing["id"],
                )
            else:
                await conn.execute(
                    """UPDATE consentimientos
                       SET estado = false, fecha_revocacion = NOW()
                       WHERE id = $1""",
                    existing["id"],
                )
        else:
            # Crear nuevo registro de consentimiento
            if body.activo:
                await conn.execute(
                    """INSERT INTO consentimientos (usuario_id, finalidad, estado, es_obligatorio, fecha_otorgamiento)
                       VALUES ($1, $2, true, false, NOW())""",
                    conductor_id, body.finalidad,
                )
            else:
                await conn.execute(
                    """INSERT INTO consentimientos (usuario_id, finalidad, estado, es_obligatorio, fecha_revocacion)
                       VALUES ($1, $2, false, false, NOW())""",
                    conductor_id, body.finalidad,
                )

        await _registrar_auditoria(
            conn, conductor_id, "arco_oposicion",
            {"finalidad": body.finalidad, "nuevo_estado": body.activo},
            request.client.host if request.client else None,
            request.headers.get("user-agent"),
        )

    estado_texto = "otorgado" if body.activo else "revocado"
    return {
        "message": f"Consentimiento de {body.finalidad} {estado_texto}",
        "finalidad": body.finalidad,
        "activo": body.activo,
    }
