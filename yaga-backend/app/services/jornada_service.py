"""
YAGA PROJECT - Servicio de Jornadas
Copyright (c) 2026 YAGA Project
"""
from services.database import get_pool
from services.nlp.classifier import ClassificationResult
from services.nlp.intent_catalog import DriverIntent
from datetime import date


async def get_or_create_jornada(conductor_id: str = "default") -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id FROM jornadas
            WHERE conductor_id = $1 AND fecha = $2 AND estado = 'activa'
            """,
            conductor_id, date.today()
        )
        if row:
            return str(row["id"])

        row = await conn.fetchrow(
            """
            INSERT INTO jornadas (conductor_id, fecha, inicio, estado)
            VALUES ($1, $2, NOW(), 'activa')
            RETURNING id
            """,
            conductor_id, date.today()
        )
        return str(row["id"])


async def registrar_viaje(jornada_id: str, entities) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO viajes (jornada_id, plataforma, monto, metodo_pago, propina)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, monto, plataforma, metodo_pago, propina, created_at
            """,
            jornada_id,
            entities.plataforma or "uber",
            entities.monto or 0,
            entities.metodo_pago or "efectivo",
            entities.propina or 0,
        )
        return dict(row)


async def registrar_gasto(jornada_id: str, entities) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO gastos (jornada_id, categoria, monto)
            VALUES ($1, $2, $3)
            RETURNING id, categoria, monto, created_at
            """,
            jornada_id,
            entities.categoria_gasto or "otro",
            entities.monto or 0,
        )
        return dict(row)


async def get_resumen_jornada(conductor_id: str = "default") -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        jornada = await conn.fetchrow(
            """
            SELECT id, inicio FROM jornadas
            WHERE conductor_id = $1 AND fecha = $2 AND estado = 'activa'
            """,
            conductor_id, date.today()
        )
        if not jornada:
            return {"error": "No hay jornada activa hoy"}

        jornada_id = jornada["id"]

        viajes = await conn.fetch(
            "SELECT monto, propina, plataforma, metodo_pago FROM viajes WHERE jornada_id = $1",
            jornada_id
        )
        gastos = await conn.fetch(
            "SELECT monto, categoria FROM gastos WHERE jornada_id = $1",
            jornada_id
        )

        total_viajes = sum(float(v["monto"]) + float(v["propina"]) for v in viajes)
        total_gastos = sum(float(g["monto"]) for g in gastos)
        ganancia_neta = total_viajes - total_gastos

        return {
            "fecha": str(date.today()),
            "inicio": str(jornada["inicio"]),
            "total_viajes": len(viajes),
            "ingresos_brutos": round(total_viajes, 2),
            "total_gastos": round(total_gastos, 2),
            "ganancia_neta": round(ganancia_neta, 2),
            "viajes_detalle": [dict(v) for v in viajes],
            "gastos_detalle": [dict(g) for g in gastos],
        }
