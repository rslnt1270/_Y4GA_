# © YAGA Project — Todos los derechos reservados
"""
gps.py — Endpoints de telemetría GPS para jornadas activas.
- POST /api/v1/gps/batch   → bulk insert de hasta 500 puntos
- POST /api/v1/jornada/cerrar-v2 → cierre con cálculo de distancia real
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import datetime, timezone
import logging

from dependencies import get_current_user
from services.gps_service import (
    batch_insert_gps,
    cerrar_jornada_con_gps,
    get_gps_historial,
    get_resumen_jornadas_con_gps,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────

class GPSPoint(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0)
    lng: float = Field(..., ge=-180.0, le=180.0)
    vel_kmh: Optional[float] = Field(None, ge=0, le=400)
    precision_m: Optional[float] = Field(None, ge=0)
    ts: Optional[datetime] = None

    @field_validator('ts', mode='before')
    @classmethod
    def ts_default_now(cls, v):
        return v or datetime.now(timezone.utc)


class GPSBatchRequest(BaseModel):
    jornada_id: str
    puntos: List[GPSPoint] = Field(..., min_length=1, max_length=500)


class GPSBatchResponse(BaseModel):
    insertados: int
    jornada_id: str
    mensaje: str


class CierreJornadaResponse(BaseModel):
    status: str
    jornada_id: str
    distancia_gps_km: float
    total_ingresos: float
    total_gastos: float
    ganancia_neta: float
    viajes: int
    duracion_min: float
    eficiencia_mxn_km: Optional[float]


class GPSPuntoDescifrado(BaseModel):
    lat: float
    lng: float
    vel_kmh: Optional[float]
    ts: str


class GPSHistorialResponse(BaseModel):
    jornada_id: str
    puntos: List[GPSPuntoDescifrado]
    total_puntos: int


class JornadaGPSResumen(BaseModel):
    jornada_id: str
    fecha: str
    estado: str
    total_puntos: int


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/api/v1/gps/batch",
    response_model=GPSBatchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Bulk insert de puntos GPS",
    tags=["GPS"],
)
async def gps_batch(
    body: GPSBatchRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Recibe hasta 500 puntos GPS y los inserta en bulk en jornada_gps_logs.
    Las coordenadas se cifran AES-256 en la capa de servicio antes de persistir.
    Rate limit: 60 req/min por usuario (aplicado en middleware slowapi).
    """
    try:
        n = await batch_insert_gps(
            jornada_id=body.jornada_id,
            conductor_id=str(current_user["id"]),
            puntos=body.puntos,
        )
        return GPSBatchResponse(
            insertados=n,
            jornada_id=body.jornada_id,
            mensaje=f"{n} puntos GPS registrados correctamente",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Error GPS batch: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno al registrar GPS")


@router.get(
    "/api/v1/gps/historial/{jornada_id}",
    response_model=GPSHistorialResponse,
    summary="Puntos GPS descifrados de una jornada para visualización",
    tags=["GPS"],
)
async def gps_historial(
    jornada_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Devuelve los puntos GPS descifrados de una jornada específica.
    Valida que la jornada pertenezca al conductor autenticado.
    Las coordenadas se descifran en memoria — nunca persisten en claro.
    """
    try:
        puntos = await get_gps_historial(jornada_id, str(current_user["id"]))
        return GPSHistorialResponse(
            jornada_id=jornada_id,
            puntos=puntos,
            total_puntos=len(puntos),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Error GPS historial: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno al obtener historial GPS")


@router.get(
    "/api/v1/gps/resumen-jornadas",
    response_model=List[JornadaGPSResumen],
    summary="Jornadas con GPS registrado (sin coordenadas)",
    tags=["GPS"],
)
async def gps_resumen_jornadas(
    current_user: dict = Depends(get_current_user),
):
    """
    Retorna metadatos de jornadas que tienen puntos GPS.
    Sin coordenadas — para poblar el selector de la vista Analítica.
    """
    try:
        return await get_resumen_jornadas_con_gps(str(current_user["id"]))
    except Exception as e:
        logger.error("Error GPS resumen jornadas: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno al obtener resumen de jornadas")


@router.post(
    "/api/v1/jornada/cerrar-v2",
    response_model=CierreJornadaResponse,
    summary="Cierre de jornada con distancia GPS real",
    tags=["Jornada"],
)
async def cerrar_jornada_v2(
    current_user: dict = Depends(get_current_user),
):
    """
    Cierra la jornada activa del conductor.
    Calcula distancia total desde GPS logs con geopy (Haversine).
    Calcula ganancia_neta = ingresos - gastos.
    Calcula eficiencia MXN/km usando distancia GPS real.
    """
    try:
        resultado = await cerrar_jornada_con_gps(conductor_id=str(current_user["id"]))
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Error cierre jornada v2: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno al cerrar jornada")
