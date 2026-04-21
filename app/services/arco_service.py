# © YAGA Project — Todos los derechos reservados
"""
services/arco_service.py — Derechos ARCO bajo LFPDPPP.

Implementa las cuatro operaciones de Acceso, Rectificación, Cancelación y
Oposición sobre los datos personales de un conductor autenticado.

Reglas clave:
  - Los datos PII se descifran en capa de aplicación con core.crypto
    (AES-256-GCM). NUNCA se usa pgp_sym_encrypt.
  - Rectificación actualiza email/nombre y re-cifra los campos *_cifrado.
  - Cancelación hace soft delete (deleted_at = NOW()) y anonimiza PII
    con placeholders. Los registros transaccionales (viajes, gastos,
    jornadas) se retienen 7 años conforme a obligaciones fiscales.
  - Oposición solo aplica a finalidades secundarias (marketing,
    investigacion). La finalidad "operacion" es obligatoria y no
    puede revocarse.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException

from core.crypto import encrypt_value, decrypt_value
from services.database import get_pool


# Finalidades reconocidas por LFPDPPP en YAGA
FINALIDADES_VALIDAS = {"operacion", "marketing", "investigacion"}
FINALIDADES_SECUNDARIAS = {"marketing", "investigacion"}


async def get_datos_acceso(usuario_id: str) -> dict:
    """
    Derecho de ACCESO — retorna los datos personales descifrados del usuario
    junto con un resumen de su actividad transaccional.

    Args:
        usuario_id: UUID del conductor autenticado (string).

    Returns:
        dict con estructura:
          {
            "datos_personales": {id, nombre, email, phone, created_at},
            "resumen_transaccional": {total_viajes, total_jornadas, total_gastos},
            "consentimientos": [{finalidad, estado, es_obligatorio, ...}]
          }

    Raises:
        HTTPException 404: Si el usuario no existe o fue eliminado.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, nombre, email, email_cifrado, phone, phone_cifrado,
                   created_at, deleted_at
            FROM usuarios
            WHERE id = $1::uuid
            """,
            usuario_id,
        )
        if not row or row["deleted_at"] is not None:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        # Priorizar el valor descifrado; si falla, usar el texto plano
        email_claro: Optional[str] = row["email"]
        if row["email_cifrado"]:
            try:
                email_claro = decrypt_value(bytes(row["email_cifrado"]))
            except Exception:
                pass

        phone_claro: Optional[str] = row["phone"]
        if row["phone_cifrado"]:
            try:
                phone_claro = decrypt_value(bytes(row["phone_cifrado"]))
            except Exception:
                pass

        total_viajes = await conn.fetchval(
            "SELECT COUNT(*) FROM viajes WHERE usuario_id = $1::uuid",
            usuario_id,
        ) or 0
        total_jornadas = await conn.fetchval(
            "SELECT COUNT(*) FROM jornadas WHERE usuario_id = $1::uuid",
            usuario_id,
        ) or 0
        total_gastos = await conn.fetchval(
            "SELECT COUNT(*) FROM gastos WHERE usuario_id = $1::uuid",
            usuario_id,
        ) or 0

        consentimientos = await conn.fetch(
            """
            SELECT finalidad, estado, es_obligatorio,
                   fecha_otorgamiento, fecha_revocacion
            FROM consentimientos
            WHERE usuario_id = $1::uuid
            ORDER BY finalidad
            """,
            usuario_id,
        )

    return {
        "datos_personales": {
            "id": str(row["id"]),
            "nombre": row["nombre"],
            "email": email_claro,
            "phone": phone_claro,
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        },
        "resumen_transaccional": {
            "total_viajes": int(total_viajes),
            "total_jornadas": int(total_jornadas),
            "total_gastos": int(total_gastos),
        },
        "consentimientos": [
            {
                "finalidad": c["finalidad"],
                "estado": bool(c["estado"]),
                "es_obligatorio": bool(c["es_obligatorio"]),
                "fecha_otorgamiento": (
                    c["fecha_otorgamiento"].isoformat()
                    if c["fecha_otorgamiento"]
                    else None
                ),
                "fecha_revocacion": (
                    c["fecha_revocacion"].isoformat()
                    if c["fecha_revocacion"]
                    else None
                ),
            }
            for c in consentimientos
        ],
    }


async def rectificar_datos(
    usuario_id: str,
    email: Optional[str],
    nombre: Optional[str],
) -> dict:
    """
    Derecho de RECTIFICACIÓN — actualiza email y/o nombre del usuario,
    re-cifrando los campos *_cifrado con una IV nueva.

    Args:
        usuario_id: UUID del conductor.
        email:      Nuevo email (opcional). Se normaliza a minúsculas.
        nombre:     Nuevo nombre (opcional).

    Returns:
        dict con los campos actualizados.

    Raises:
        HTTPException 400: Si no se proporciona ningún campo o si el email
                           ya pertenece a otro usuario activo.
        HTTPException 404: Si el usuario no existe.
    """
    if not email and not nombre:
        raise HTTPException(
            status_code=400,
            detail="Debes enviar al menos un campo a rectificar (email o nombre).",
        )

    email_norm: Optional[str] = email.lower().strip() if email else None
    nombre_norm: Optional[str] = nombre.strip() if nombre else None

    pool = await get_pool()
    async with pool.acquire() as conn:
        existe = await conn.fetchval(
            "SELECT id FROM usuarios WHERE id = $1::uuid AND deleted_at IS NULL",
            usuario_id,
        )
        if not existe:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        if email_norm:
            ocupado = await conn.fetchval(
                """
                SELECT id FROM usuarios
                WHERE email = $1 AND id <> $2::uuid AND deleted_at IS NULL
                """,
                email_norm,
                usuario_id,
            )
            if ocupado:
                raise HTTPException(
                    status_code=400,
                    detail="El email ya está registrado por otro usuario.",
                )

            email_cifrado = encrypt_value(email_norm)
            await conn.execute(
                """
                UPDATE usuarios
                SET email = $1, email_cifrado = $2, updated_at = NOW()
                WHERE id = $3::uuid
                """,
                email_norm,
                email_cifrado,
                usuario_id,
            )

        if nombre_norm:
            await conn.execute(
                """
                UPDATE usuarios
                SET nombre = $1, updated_at = NOW()
                WHERE id = $2::uuid
                """,
                nombre_norm,
                usuario_id,
            )

    return {
        "status": "rectificado",
        "usuario_id": usuario_id,
        "email": email_norm,
        "nombre": nombre_norm,
    }


async def cancelar_cuenta(usuario_id: str) -> dict:
    """
    Derecho de CANCELACIÓN — soft delete con anonimización de PII.

    Marca deleted_at = NOW(), reemplaza email por un placeholder determinista,
    phone por "0000000000", y re-cifra ambos campos con la clave actual.
    Los registros transaccionales (viajes, gastos, jornadas) se retienen
    por obligaciones fiscales (CFF art. 30: 5 años mínimo, YAGA aplica 7).

    Args:
        usuario_id: UUID del conductor.

    Returns:
        dict con el email placeholder final.

    Raises:
        HTTPException 404: Si el usuario no existe o ya fue cancelado.
    """
    pool = await get_pool()
    placeholder_email = f"eliminado_{usuario_id}@arco.yaga"
    placeholder_phone = "0000000000"

    async with pool.acquire() as conn:
        existe = await conn.fetchval(
            "SELECT id FROM usuarios WHERE id = $1::uuid AND deleted_at IS NULL",
            usuario_id,
        )
        if not existe:
            raise HTTPException(
                status_code=404, detail="Usuario no encontrado o ya cancelado"
            )

        # Liberar la unicidad del phone real antes de reasignarlo:
        # otros usuarios cancelados también usan "0000000000", por lo que
        # debemos limpiar el phone a NULL para no chocar con la UNIQUE.
        email_cifrado = encrypt_value(placeholder_email)
        phone_cifrado = encrypt_value(placeholder_phone)

        await conn.execute(
            """
            UPDATE usuarios
            SET deleted_at    = NOW(),
                updated_at    = NOW(),
                email         = $1,
                email_cifrado = $2,
                phone         = NULL,
                phone_cifrado = $3,
                nombre        = 'Usuario Eliminado'
            WHERE id = $4::uuid
            """,
            placeholder_email,
            email_cifrado,
            phone_cifrado,
            usuario_id,
        )

    return {
        "status": "cancelado",
        "usuario_id": usuario_id,
        "email_anonimizado": placeholder_email,
        "mensaje": (
            "Tu cuenta ha sido cancelada. Los registros transaccionales "
            "se retienen 7 años por obligaciones fiscales (CFF art. 30)."
        ),
    }


async def gestionar_oposicion(
    usuario_id: str,
    finalidad: str,
    activo: bool,
) -> dict:
    """
    Derecho de OPOSICIÓN — activa o revoca un consentimiento secundario.

    La finalidad "operacion" es obligatoria y nunca puede revocarse.
    Crea el registro si no existe (UPSERT sobre usuario_id+finalidad).

    Args:
        usuario_id: UUID del conductor.
        finalidad:  Una de {"marketing", "investigacion"}.
        activo:     True para otorgar, False para revocar.

    Returns:
        dict con el estado final del consentimiento.

    Raises:
        HTTPException 400: Finalidad inválida o intento de revocar "operacion".
    """
    if finalidad not in FINALIDADES_VALIDAS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Finalidad inválida. Valores permitidos: "
                f"{sorted(FINALIDADES_VALIDAS)}"
            ),
        )

    if finalidad == "operacion":
        raise HTTPException(
            status_code=400,
            detail=(
                "La finalidad 'operacion' es obligatoria para la prestación "
                "del servicio y no puede revocarse."
            ),
        )

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO consentimientos
                (usuario_id, finalidad, estado, es_obligatorio,
                 fecha_otorgamiento, fecha_revocacion)
            VALUES ($1::uuid, $2, $3, FALSE,
                    CASE WHEN $3 THEN NOW() ELSE NULL END,
                    CASE WHEN $3 THEN NULL ELSE NOW() END)
            ON CONFLICT (usuario_id, finalidad) DO UPDATE SET
                estado             = EXCLUDED.estado,
                fecha_otorgamiento = CASE
                    WHEN EXCLUDED.estado THEN NOW()
                    ELSE consentimientos.fecha_otorgamiento
                END,
                fecha_revocacion   = CASE
                    WHEN EXCLUDED.estado THEN NULL
                    ELSE NOW()
                END
            RETURNING finalidad, estado, fecha_otorgamiento, fecha_revocacion
            """,
            usuario_id,
            finalidad,
            activo,
        )

    return {
        "status": "actualizado",
        "finalidad": row["finalidad"],
        "estado": bool(row["estado"]),
        "fecha_otorgamiento": (
            row["fecha_otorgamiento"].isoformat()
            if row["fecha_otorgamiento"]
            else None
        ),
        "fecha_revocacion": (
            row["fecha_revocacion"].isoformat()
            if row["fecha_revocacion"]
            else None
        ),
    }
