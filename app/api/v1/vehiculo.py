"""
YAGA PROJECT - Endpoints de Vehículo (Sprint 3)
Copyright (c) 2026 YAGA Project
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from services.vehiculo_service import (
    get_vehiculo,
    actualizar_km,
    actualizar_perfil,
    registrar_aceite,
    registrar_servicio,
)

router = APIRouter()


class KmUpdate(BaseModel):
    km: float
    conductor_id: str = "default"


class PerfilVehiculo(BaseModel):
    marca: str
    modelo: str
    anio: int
    color: Optional[str] = None
    placa: Optional[str] = None
    conductor_id: str = "default"


@router.get("/vehiculo")
async def estado_vehiculo(conductor_id: str = "default"):
    return await get_vehiculo(conductor_id)


@router.put("/vehiculo/perfil")
async def update_perfil(body: PerfilVehiculo):
    return await actualizar_perfil(
        body.conductor_id, body.marca, body.modelo,
        body.anio, body.color, body.placa
    )


@router.post("/vehiculo/km")
async def update_km(body: KmUpdate):
    return await actualizar_km(body.conductor_id, body.km)


@router.post("/vehiculo/aceite")
async def cambio_aceite(conductor_id: str = "default"):
    return await registrar_aceite(conductor_id)


@router.post("/vehiculo/servicio")
async def servicio_completo(conductor_id: str = "default"):
    return await registrar_servicio(conductor_id)
