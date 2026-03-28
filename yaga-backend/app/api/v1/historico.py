"""
YAGA PROJECT - Endpoints de Historico de Viajes
POST /api/v1/historico/import/json  — importar JSON del extractor Uber
GET  /api/v1/historico/stats        — estadisticas del historico del conductor
Copyright (c) 2026 YAGA Project
"""
import json
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Header, Query
from jose import JWTError
from services.auth_service import decode_token
from services.historico_service import import_viajes_json, get_stats_historico, get_mapa_data, get_ganancias_semanal

router = APIRouter()


async def get_conductor_id(authorization: Optional[str] = Header(None)) -> str:
    """Extrae conductor_id del Bearer JWT en el header Authorization."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token requerido. Header: Authorization: Bearer <token>")
    try:
        payload = decode_token(authorization[7:])
        return payload["sub"]
    except (JWTError, KeyError):
        raise HTTPException(status_code=401, detail="Token invalido o expirado")


@router.post("/historico/import/json", status_code=200)
async def import_json(
    file: UploadFile = File(..., description="JSON exportado del extractor Uber o DiDi (lista de viajes)"),
    platform: str = Query("auto", description="Plataforma: 'uber', 'didi' o 'auto' (deteccion automatica)"),
    conductor_id: str = Depends(get_conductor_id),
):
    """
    Importa el archivo JSON generado por el extractor Uber al historico del conductor.

    El archivo debe ser una lista de viajes del endpoint `getWebActivityFeed` de Uber.
    Los viajes duplicados (mismo trip_id) se omiten automaticamente.
    """
    if not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos .json")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10 MB max
        raise HTTPException(status_code=413, detail="Archivo demasiado grande (max 10MB)")

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"JSON invalido: {e}")

    if not isinstance(data, list):
        raise HTTPException(status_code=400, detail="El JSON debe ser una lista de viajes (array)")

    if len(data) == 0:
        raise HTTPException(status_code=400, detail="El archivo esta vacio")

    resultado = await import_viajes_json(data, conductor_id, platform)

    return {
        "status": "ok",
        "archivo": file.filename,
        "conductor_id": conductor_id,
        "plataforma": platform,
        "resultado": resultado,
        "mensaje": f"{resultado['insertados']} viajes nuevos importados. {resultado['duplicados']} ya existian.",
    }


@router.get("/historico/mapa")
async def mapa_historico(conductor_id: str = Depends(get_conductor_id)):
    """
    Retorna lista de viajes con coordenadas GPS del punto de recogida.
    Usado por el mapa interactivo del frontend.
    """
    viajes = await get_mapa_data(conductor_id)
    if not viajes:
        return {"viajes": [], "total": 0, "mensaje": "Sin datos geograficos. Importa tu historico de Uber."}
    return {"viajes": viajes, "total": len(viajes)}


@router.get("/historico/semanal")
async def semanal_historico(conductor_id: str = Depends(get_conductor_id)):
    """
    Retorna ingresos agrupados por día de la semana (últimos 90 días).
    Usado por la gráfica de barras en la pantalla Ganancias.
    """
    dias = await get_ganancias_semanal(conductor_id)
    return {"dias": dias, "conductor_id": conductor_id}


@router.get("/historico/stats")
async def stats_historico(conductor_id: str = Depends(get_conductor_id)):
    """
    Retorna estadisticas del historico de viajes del conductor autenticado.
    Incluye total, ingresos, promedio por viaje, distancia y rango de fechas.
    """
    stats = await get_stats_historico(conductor_id)
    if stats["total_viajes"] == 0:
        return {
            "conductor_id": conductor_id,
            "total_viajes": 0,
            "mensaje": "No hay historico importado. Usa POST /api/v1/historico/import/json para importar tus viajes de Uber.",
        }
    return {"conductor_id": conductor_id, **stats}
