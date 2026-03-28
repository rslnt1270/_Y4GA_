from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def info_vehiculo():
    return {"mensaje": "Módulo de vehículo en construcción para YAGA"}
