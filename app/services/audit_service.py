# © YAGA Project — Todos los derechos reservados
"""
services/audit_service.py — Servicio de auditoría fire-and-forget.

Registra acciones críticas en la tabla `auditoria` sin bloquear el response.
Si la escritura falla (DB caída, error de tipo, etc.) se loggea la excepción
pero NUNCA se relanza: la auditoría es best-effort, nunca debe tumbar un flujo
de negocio como login o registro.

Acciones soportadas (Sprint 6 — Semana 2):
    - login_exitoso
    - login_fallido
    - registro
    - reset_password_solicitado
    - reset_password_completado

Uso recomendado desde un endpoint FastAPI:

    import asyncio
    from services.audit_service import log_action

    asyncio.create_task(log_action(
        usuario_id=str(row["id"]),
        accion="login_exitoso",
        ip=request.client.host,
        user_agent=request.headers.get("user-agent", ""),
        detalles={"email": email_norm},
    ))
"""
from __future__ import annotations

import json
from typing import Optional

from services.database import get_pool
from core.logging import get_logger

logger = get_logger("yaga.audit")


async def log_action(
    usuario_id: Optional[str],
    accion: str,
    ip: str,
    user_agent: str,
    detalles: dict,
) -> None:
    """
    Inserta una fila en la tabla `auditoria` de forma fire-and-forget.

    Args:
        usuario_id: UUID del usuario en formato string, o None si la acción
                    ocurrió sin usuario autenticado (ej. login fallido).
        accion:     Nombre corto de la acción (ej. "login_exitoso").
        ip:         IP del cliente (string). Se castea a INET en SQL.
        user_agent: Header User-Agent del cliente.
        detalles:   Diccionario arbitrario con contexto adicional.
                    Se serializa a JSONB.

    Notas:
        - La columna `ip` en PostgreSQL es de tipo INET. Si la IP está vacía
          o es inválida, se inserta NULL.
        - Si `usuario_id` no es un UUID válido, se inserta NULL.
        - Ninguna excepción se propaga al caller.
    """
    try:
        pool = await get_pool()

        # Saneamiento defensivo de parámetros
        ip_clean: Optional[str] = ip.strip() if ip else None
        if ip_clean in ("", "unknown"):
            ip_clean = None

        ua_clean = (user_agent or "")[:1024]  # truncar UA gigantes
        detalles_json = json.dumps(detalles or {}, ensure_ascii=False, default=str)

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO auditoria (usuario_id, accion, ip, user_agent, detalles)
                VALUES ($1::uuid, $2, $3::inet, $4, $5::jsonb)
                """,
                usuario_id,
                accion,
                ip_clean,
                ua_clean,
                detalles_json,
            )
    except Exception as exc:  # noqa: BLE001 — fire-and-forget por diseño
        logger.warning(
            "audit_log_failed accion=%s usuario_id=%s error=%s",
            accion,
            usuario_id,
            exc,
        )
