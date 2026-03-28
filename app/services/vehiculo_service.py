"""
YAGA PROJECT - Servicio de Vehículo (Sprint 3)
Copyright (c) 2026 YAGA Project
"""
from services.database import get_pool


async def get_vehiculo(conductor_id: str = "default") -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM vehiculos WHERE conductor_id = $1",
            conductor_id
        )
        if not row:
            return {"error": "Vehículo no registrado"}

        v = dict(row)
        km_desde_aceite   = float(v["km_actuales"]) - float(v["km_ultimo_aceite"])
        km_desde_servicio = float(v["km_actuales"]) - float(v["km_ultimo_servicio"])

        alerta_aceite   = km_desde_aceite   >= 4500
        alerta_servicio = km_desde_servicio >= 9000

        return {
            "conductor_id":       v["conductor_id"],
            "marca":              v.get("marca"),
            "modelo":             v.get("modelo"),
            "anio":               v.get("anio"),
            "color":              v.get("color"),
            "placa":              v.get("placa"),
            "km_actuales":        float(v["km_actuales"]),
            "km_ultimo_aceite":   float(v["km_ultimo_aceite"]),
            "km_ultimo_servicio": float(v["km_ultimo_servicio"]),
            "rendimiento_kmlt":   float(v["rendimiento_kmlt"]),
            "km_desde_aceite":    round(km_desde_aceite, 1),
            "km_desde_servicio":  round(km_desde_servicio, 1),
            "alerta_aceite":      alerta_aceite,
            "alerta_servicio":    alerta_servicio,
            "updated_at":         str(v["updated_at"]),
        }


async def actualizar_perfil(
    conductor_id: str,
    marca: str,
    modelo: str,
    anio: int,
    color: str | None = None,
    placa: str | None = None,
) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE vehiculos
               SET marca = $1, modelo = $2, anio = $3, color = $4, placa = $5,
                   updated_at = NOW()
             WHERE conductor_id = $6
            """,
            marca, modelo, anio, color, placa, conductor_id,
        )
        # Si no existe fila, insertar con valores base
        if result == "UPDATE 0":
            await conn.execute(
                """
                INSERT INTO vehiculos
                    (conductor_id, marca, modelo, anio, color, placa,
                     km_actuales, km_ultimo_aceite, km_ultimo_servicio, rendimiento_kmlt)
                VALUES ($1, $2, $3, $4, $5, $6, 0, 0, 0, 10.0)
                """,
                conductor_id, marca, modelo, anio, color, placa,
            )
    return await get_vehiculo(conductor_id)


async def actualizar_km(conductor_id: str, km_nuevos: float) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE vehiculos
               SET km_actuales = $1, updated_at = NOW()
             WHERE conductor_id = $2
            """,
            km_nuevos, conductor_id,
        )
        if result == "UPDATE 0":
            return {"error": "Vehículo no encontrado"}
    return await get_vehiculo(conductor_id)


async def registrar_aceite(conductor_id: str) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE vehiculos
               SET km_ultimo_aceite = km_actuales, updated_at = NOW()
             WHERE conductor_id = $1
            """,
            conductor_id,
        )
    return await get_vehiculo(conductor_id)


async def registrar_servicio(conductor_id: str) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE vehiculos
               SET km_ultimo_servicio = km_actuales, updated_at = NOW()
             WHERE conductor_id = $1
            """,
            conductor_id,
        )
    return await get_vehiculo(conductor_id)
