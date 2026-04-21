# © YAGA Project — Todos los derechos reservados
"""
api/v1/arco.py — Endpoints de derechos ARCO bajo LFPDPPP.

Todos los endpoints requieren autenticación Sistema A (HS256 via
get_current_user) y están limitados a 5 req/min por IP.

Cada operación se registra en `auditoria` con accion = arco_*
vía audit_service (fire-and-forget).
"""
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from core.limiter import limiter
from dependencies import get_current_user
from services.arco_service import (
    cancelar_cuenta,
    gestionar_oposicion,
    get_datos_acceso,
    rectificar_datos,
)
from services.audit_service import log_action


router = APIRouter()


def _client_ip(request: Request) -> str:
    """Obtiene la IP real respetando X-Forwarded-For del proxy."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


def _client_ua(request: Request) -> str:
    """User-Agent del cliente."""
    return request.headers.get("user-agent", "")


# ── Pydantic bodies ──────────────────────────────────────────────────────────


class RectificacionBody(BaseModel):
    """Body para PUT /arco/rectificacion — al menos un campo."""

    email: Optional[str] = Field(default=None, max_length=255)
    nombre: Optional[str] = Field(default=None, max_length=120)


class OposicionBody(BaseModel):
    """Body para POST /arco/oposicion — finalidad secundaria + estado."""

    finalidad: str = Field(..., description="marketing | investigacion")
    activo: bool = Field(..., description="True = otorgar, False = revocar")


# ── GET /arco/acceso ─────────────────────────────────────────────────────────


@router.get("/arco/acceso")
@limiter.limit("5/minute")
async def arco_acceso(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Derecho de ACCESO — retorna datos personales descifrados y resumen
    transaccional del conductor autenticado.
    """
    usuario_id = str(current_user["id"])
    datos = await get_datos_acceso(usuario_id)

    asyncio.create_task(
        log_action(
            usuario_id=usuario_id,
            accion="arco_acceso",
            ip=_client_ip(request),
            user_agent=_client_ua(request),
            detalles={"total_viajes": datos["resumen_transaccional"]["total_viajes"]},
        )
    )
    return datos


# ── PUT /arco/rectificacion ──────────────────────────────────────────────────


@router.put("/arco/rectificacion")
@limiter.limit("5/minute")
async def arco_rectificacion(
    request: Request,
    body: RectificacionBody,
    current_user: dict = Depends(get_current_user),
):
    """
    Derecho de RECTIFICACIÓN — actualiza email y/o nombre, re-cifrando
    los campos PII correspondientes.
    """
    usuario_id = str(current_user["id"])
    resultado = await rectificar_datos(
        usuario_id=usuario_id,
        email=body.email,
        nombre=body.nombre,
    )

    asyncio.create_task(
        log_action(
            usuario_id=usuario_id,
            accion="arco_rectificacion",
            ip=_client_ip(request),
            user_agent=_client_ua(request),
            detalles={
                "cambio_email": body.email is not None,
                "cambio_nombre": body.nombre is not None,
            },
        )
    )
    return resultado


# ── POST /arco/cancelacion ───────────────────────────────────────────────────


@router.post("/arco/cancelacion")
@limiter.limit("5/minute")
async def arco_cancelacion(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Derecho de CANCELACIÓN — soft delete con anonimización de PII.
    Los registros transaccionales se retienen 7 años por obligaciones fiscales.
    """
    usuario_id = str(current_user["id"])
    resultado = await cancelar_cuenta(usuario_id)

    asyncio.create_task(
        log_action(
            usuario_id=usuario_id,
            accion="arco_cancelacion",
            ip=_client_ip(request),
            user_agent=_client_ua(request),
            detalles={"email_anonimizado": resultado["email_anonimizado"]},
        )
    )
    return resultado


# ── POST /arco/oposicion ─────────────────────────────────────────────────────


@router.post("/arco/oposicion")
@limiter.limit("5/minute")
async def arco_oposicion(
    request: Request,
    body: OposicionBody,
    current_user: dict = Depends(get_current_user),
):
    """
    Derecho de OPOSICIÓN — activa/revoca un consentimiento secundario
    (marketing o investigacion). La finalidad "operacion" no puede
    revocarse.
    """
    usuario_id = str(current_user["id"])
    resultado = await gestionar_oposicion(
        usuario_id=usuario_id,
        finalidad=body.finalidad,
        activo=body.activo,
    )

    asyncio.create_task(
        log_action(
            usuario_id=usuario_id,
            accion="arco_oposicion",
            ip=_client_ip(request),
            user_agent=_client_ua(request),
            detalles={"finalidad": body.finalidad, "activo": body.activo},
        )
    )
    return resultado
