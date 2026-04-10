# © YAGA Project — Todos los derechos reservados
"""
api/v1/consentimientos.py — Gestión de consentimientos LFPDPPP.

Cada usuario puede tener hasta 3 consentimientos:
    - operacion     (es_obligatorio=TRUE, no puede desactivarse)
    - marketing     (opt-out)
    - investigacion (opt-out)

La tabla `consentimientos` usa la columna `estado` (boolean) para reflejar
si el consentimiento está activo, con `fecha_otorgamiento` y
`fecha_revocacion` como marcas de tiempo.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core.limiter import limiter
from dependencies import get_current_user
from services.database import get_pool


router = APIRouter()

FINALIDADES_VALIDAS = {"operacion", "marketing", "investigacion"}


class ConsentimientoBody(BaseModel):
    """Body para POST /consentimientos — crea o actualiza un consentimiento."""

    finalidad: str = Field(..., description="operacion | marketing | investigacion")
    estado: bool = Field(..., description="True = activo, False = revocado")


# ── GET /consentimientos ─────────────────────────────────────────────────────


@router.get("/consentimientos")
@limiter.limit("30/minute")
async def listar_consentimientos(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Lista todos los consentimientos del usuario autenticado."""
    usuario_id = str(current_user["id"])
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT finalidad, estado, es_obligatorio,
                   fecha_otorgamiento, fecha_revocacion, created_at
            FROM consentimientos
            WHERE usuario_id = $1::uuid
            ORDER BY finalidad
            """,
            usuario_id,
        )

    return {
        "usuario_id": usuario_id,
        "consentimientos": [
            {
                "finalidad": r["finalidad"],
                "estado": bool(r["estado"]),
                "es_obligatorio": bool(r["es_obligatorio"]),
                "fecha_otorgamiento": (
                    r["fecha_otorgamiento"].isoformat()
                    if r["fecha_otorgamiento"]
                    else None
                ),
                "fecha_revocacion": (
                    r["fecha_revocacion"].isoformat()
                    if r["fecha_revocacion"]
                    else None
                ),
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ],
    }


# ── POST /consentimientos ────────────────────────────────────────────────────


@router.post("/consentimientos")
@limiter.limit("10/minute")
async def upsert_consentimiento(
    request: Request,
    body: ConsentimientoBody,
    current_user: dict = Depends(get_current_user),
):
    """
    Crea o actualiza un consentimiento del usuario autenticado.

    Reglas:
      - Finalidad debe pertenecer a {operacion, marketing, investigacion}.
      - "operacion" con es_obligatorio=TRUE no puede desactivarse.
      - Si el registro no existe, se crea con es_obligatorio según finalidad.
    """
    if body.finalidad not in FINALIDADES_VALIDAS:
        raise HTTPException(
            status_code=400,
            detail=f"Finalidad inválida. Valores: {sorted(FINALIDADES_VALIDAS)}",
        )

    usuario_id = str(current_user["id"])
    es_obligatorio = body.finalidad == "operacion"

    # Bloquear desactivación de un consentimiento obligatorio
    if es_obligatorio and body.estado is False:
        raise HTTPException(
            status_code=400,
            detail=(
                "La finalidad 'operacion' es obligatoria para la prestación "
                "del servicio y no puede desactivarse."
            ),
        )

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Si ya existe y es obligatorio con estado TRUE, no permitir cambio a FALSE
        actual = await conn.fetchrow(
            """
            SELECT estado, es_obligatorio
            FROM consentimientos
            WHERE usuario_id = $1::uuid AND finalidad = $2
            """,
            usuario_id,
            body.finalidad,
        )
        if actual and actual["es_obligatorio"] and body.estado is False:
            raise HTTPException(
                status_code=400,
                detail="No se puede desactivar un consentimiento obligatorio.",
            )

        row = await conn.fetchrow(
            """
            INSERT INTO consentimientos
                (usuario_id, finalidad, estado, es_obligatorio,
                 fecha_otorgamiento, fecha_revocacion)
            VALUES ($1::uuid, $2, $3, $4,
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
            RETURNING finalidad, estado, es_obligatorio,
                      fecha_otorgamiento, fecha_revocacion
            """,
            usuario_id,
            body.finalidad,
            body.estado,
            es_obligatorio,
        )

    return {
        "status": "ok",
        "finalidad": row["finalidad"],
        "estado": bool(row["estado"]),
        "es_obligatorio": bool(row["es_obligatorio"]),
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
