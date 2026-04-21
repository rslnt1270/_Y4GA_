"""
YAGA PROJECT - Servicio de Jornadas
Copyright (c) 2026 YAGA Project
"""
from services.database import get_pool
from services.historico_service import get_promedio_historico
from services.gps_service import _calcular_distancia
from datetime import date


async def get_or_create_jornada(conductor_id: str = "default") -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM jornadas WHERE conductor_id = $1 AND fecha = $2 AND estado = 'activa'",
            conductor_id, date.today()
        )
        if row:
            return str(row["id"])
        new_id = await conn.fetchval(
            "INSERT INTO jornadas (conductor_id, fecha, estado, inicio) VALUES ($1, $2, 'activa', NOW()) RETURNING id",
            conductor_id, date.today()
        )
        return str(new_id)


async def registrar_viaje(jornada_id: str, entities) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO viajes (jornada_id, monto, propina, plataforma, metodo_pago) VALUES ($1, $2, $3, $4, $5) RETURNING id, monto, propina, plataforma, metodo_pago",
            jornada_id,
            float(entities.monto or 0),
            float(entities.propina or 0),
            str(entities.plataforma or "uber").lower(),
            str(entities.metodo_pago or "app").lower()
        )
        return dict(row)


async def registrar_gasto(jornada_id: str, entities) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO gastos (jornada_id, monto, categoria) VALUES ($1, $2, $3) RETURNING id, monto, categoria",
            jornada_id,
            float(entities.monto or 0),
            str(entities.categoria_gasto or "otro").lower()
        )
        return dict(row)


async def get_resumen_jornada(conductor_id: str = "default") -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        jornada = await conn.fetchrow(
            "SELECT id, inicio FROM jornadas WHERE conductor_id = $1 AND fecha = $2 AND estado = 'activa'",
            conductor_id, date.today()
        )
        if not jornada:
            return {"error": "No hay jornada activa hoy"}

        viajes = await conn.fetch("SELECT monto, propina, plataforma, metodo_pago FROM viajes WHERE jornada_id = $1", jornada["id"])
        gastos = await conn.fetch("SELECT monto, categoria FROM gastos WHERE jornada_id = $1", jornada["id"])

        # Distancia GPS acumulada en jornada activa
        gps_rows = await conn.fetch(
            "SELECT lat_cifrado, lng_cifrado, ts FROM jornada_gps_logs WHERE jornada_id = $1 ORDER BY ts ASC",
            jornada["id"],
        )
        distancia_km = _calcular_distancia(gps_rows)

        total_viajes = sum(float(v["monto"]) + float(v["propina"] or 0) for v in viajes)
        total_gastos = sum(float(g["monto"]) for g in gastos)
        ganancia_neta = round(total_viajes - total_gastos, 2)

        return {
            "fecha": str(date.today()),
            "inicio": str(jornada["inicio"]),
            "total_viajes": len(viajes),
            "ingresos_brutos": round(total_viajes, 2),
            "total_gastos": round(total_gastos, 2),
            "ganancia_neta": ganancia_neta,
            "distancia_gps_km": round(distancia_km, 2),
            "eficiencia_mxn_km": round(ganancia_neta / distancia_km, 2) if distancia_km > 0 else None,
            "viajes_detalle": [dict(v) for v in viajes],
            "gastos_detalle": [dict(g) for g in gastos],
        }


async def cerrar_jornada(conductor_id: str = "default") -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        jornada_id = await conn.fetchval(
            "UPDATE jornadas SET estado = 'cerrada', fin = NOW() WHERE conductor_id = $1 AND fecha = $2 AND estado = 'activa' RETURNING id",
            conductor_id, date.today()
        )
        return jornada_id is not None


async def get_comparativa(conductor_id: str = "default") -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        jornada = await conn.fetchrow(
            "SELECT id FROM jornadas WHERE conductor_id = $1 AND fecha = $2 AND estado = 'activa'",
            conductor_id, date.today()
        )
        if not jornada:
            return {"error": "No hay jornada activa hoy"}

        viajes = await conn.fetch("SELECT monto, propina FROM viajes WHERE jornada_id = $1", jornada["id"])
        total_hoy = sum(float(v["monto"]) + float(v["propina"] or 0) for v in viajes)
        n_viajes = len(viajes)
        promedio_hoy = round(total_hoy / n_viajes, 2) if n_viajes > 0 else 0
        promedio_historico = await get_promedio_historico(conductor_id)
        delta_pct = round((promedio_hoy - promedio_historico) / promedio_historico * 100, 1) if promedio_historico else 0

        if delta_pct >= 10:
            estado = "🔥 Excelente — estás por encima de tu promedio histórico"
        elif delta_pct >= 0:
            estado = "✅ Bien — igualando tu promedio histórico"
        elif delta_pct >= -10:
            estado = "⚠️ Por debajo — puedes mejorar"
        else:
            estado = "🔴 Jornada difícil — muy por debajo del promedio"

        return {
            "jornada_hoy": {"viajes": n_viajes, "promedio_x_viaje": promedio_hoy},
            "historico": {"promedio_x_viaje": promedio_historico},
            "comparativa": {"delta_pct": delta_pct, "estado": estado},
        }
