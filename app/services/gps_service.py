# © YAGA Project — Todos los derechos reservados
"""
gps_service.py — Lógica de negocio para GPS tracking y cierre de jornada.

Cifrado: lat/lng → AES-256 (módulo core.crypto) antes de persistir.
Distancia: Haversine via geopy sobre puntos descifrados en memoria (nunca en DB).
Bulk insert: UNNEST para insertar N filas en una sola query.
"""
import logging
from datetime import date
from typing import List, Optional

from geopy.distance import geodesic

from core.crypto import encrypt_value, decrypt_value
from services.database import get_pool

logger = logging.getLogger(__name__)


def _truncar_coordenada(valor: float, decimales: int = 4) -> float:
    """Reduce precisión a ~11 metros (4 decimales). Protege privacidad del domicilio."""
    return round(valor, decimales)


async def _filtrar_saltos(conn, jornada_id: str, puntos: list) -> list:
    """Filtra puntos con velocidad implícita > 300 km/h respecto al punto previo."""
    last = await conn.fetchrow(
        "SELECT lat_cifrado, lng_cifrado, ts FROM jornada_gps_logs WHERE jornada_id = $1 ORDER BY ts DESC LIMIT 1",
        jornada_id,
    )

    resultado = []
    prev_lat, prev_lng, prev_ts = None, None, None

    if last:
        try:
            prev_lat = float(decrypt_value(bytes(last["lat_cifrado"])))
            prev_lng = float(decrypt_value(bytes(last["lng_cifrado"])))
            prev_ts = last["ts"]
        except Exception:
            pass

    for p in puntos:
        if prev_lat is not None and prev_ts is not None:
            d = geodesic((prev_lat, prev_lng), (p.lat, p.lng)).km
            dt_h = (p.ts - prev_ts).total_seconds() / 3600
            if dt_h > 0 and (d / dt_h) > 300:
                logger.debug("Punto GPS descartado: salto %.1f km en %.1f s", d, dt_h * 3600)
                continue
        resultado.append(p)
        prev_lat, prev_lng, prev_ts = p.lat, p.lng, p.ts

    return resultado


# ── GPS Batch Insert ──────────────────────────────────────────────────────────

async def batch_insert_gps(
    jornada_id: str,
    conductor_id: str,
    puntos: List,
) -> int:
    """
    Cifra coordenadas y las inserta en bulk via UNNEST.
    Valida que la jornada_id pertenezca al conductor_id (seguridad).
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Validar ownership
        row = await conn.fetchrow(
            "SELECT id FROM jornadas WHERE id = $1 AND conductor_id = $2 AND estado = 'activa'",
            jornada_id, conductor_id,
        )
        if not row:
            raise ValueError("Jornada no encontrada o no pertenece al conductor")

        # Filtrar puntos con GPS impreciso (>50m) antes de cifrar
        puntos_validos = [p for p in puntos if p.precision_m is None or p.precision_m <= 50]
        if not puntos_validos:
            logger.debug("Todos los puntos GPS descartados por baja precisión")
            return 0

        # Filtrar saltos imposibles (>300 km/h) antes de cifrar
        puntos_validos = await _filtrar_saltos(conn, jornada_id, puntos_validos)
        if not puntos_validos:
            logger.debug("Todos los puntos GPS descartados por saltos imposibles")
            return 0

        # Cifrar coordenadas — IV único por punto
        lats_cifrado = [encrypt_value(str(p.lat)) for p in puntos_validos]
        lngs_cifrado = [encrypt_value(str(p.lng)) for p in puntos_validos]
        vels = [p.vel_kmh for p in puntos_validos]
        precs = [p.precision_m for p in puntos_validos]
        tss = [p.ts for p in puntos_validos]

        # Bulk insert via UNNEST — una sola query sin loop Python
        await conn.execute(
            """
            INSERT INTO jornada_gps_logs
                (jornada_id, lat_cifrado, lng_cifrado, vel_kmh, precision_m, ts)
            SELECT $1,
                   unnest($2::bytea[]),
                   unnest($3::bytea[]),
                   unnest($4::float8[]),
                   unnest($5::float8[]),
                   unnest($6::timestamptz[])
            """,
            jornada_id,
            lats_cifrado,
            lngs_cifrado,
            vels,
            precs,
            tss,
        )
    return len(puntos_validos)


# ── Cierre de Jornada con GPS ─────────────────────────────────────────────────

async def cerrar_jornada_con_gps(conductor_id: str) -> dict:
    """
    1. Cierra la jornada activa.
    2. Descifra GPS logs en memoria → calcula distancia Haversine.
    3. Suma ingresos y gastos → ganancia_neta.
    4. Actualiza distancia_gps_km en viajes del día (reparto proporcional).
    5. Devuelve resumen completo.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Cerrar jornada
            jornada = await conn.fetchrow(
                """
                UPDATE jornadas
                   SET estado = 'cerrada', fin = NOW()
                 WHERE conductor_id = $1 AND fecha = $2 AND estado = 'activa'
                RETURNING id, inicio, fin
                """,
                conductor_id, date.today(),
            )
            if not jornada:
                raise ValueError("No hay jornada activa para cerrar hoy")

            jornada_id = jornada["id"]
            duracion_min = 0.0
            if jornada["inicio"] and jornada["fin"]:
                delta = jornada["fin"] - jornada["inicio"]
                duracion_min = delta.total_seconds() / 60

            # Recuperar GPS logs (solo vel+ts en claro; lat/lng cifradas)
            gps_rows = await conn.fetch(
                """
                SELECT lat_cifrado, lng_cifrado, ts
                  FROM jornada_gps_logs
                 WHERE jornada_id = $1
                 ORDER BY ts ASC
                """,
                jornada_id,
            )

            # Calcular distancia descifrada en memoria — nunca persiste en claro
            distancia_km = _calcular_distancia(gps_rows)

            # Estadísticas financieras
            stats = await conn.fetchrow(
                """
                SELECT
                    COUNT(v.id)                        AS total_viajes,
                    COALESCE(SUM(v.monto), 0)          AS total_ingresos,
                    COALESCE(SUM(v.monto_final_app), 0) AS total_final_app
                FROM viajes v
                WHERE v.jornada_id = $1
                """,
                jornada_id,
            )
            gastos_row = await conn.fetchrow(
                "SELECT COALESCE(SUM(monto), 0) AS total_gastos FROM gastos WHERE jornada_id = $1",
                jornada_id,
            )

            total_ingresos = float(stats["total_ingresos"])
            total_gastos = float(gastos_row["total_gastos"])
            ganancia_neta = total_ingresos - total_gastos
            total_viajes = int(stats["total_viajes"])

            eficiencia = round(ganancia_neta / distancia_km, 2) if distancia_km > 0 else None

            # Actualizar distancia_gps_km + ganancia_real en todos los viajes de la jornada
            if distancia_km > 0 and total_viajes > 0:
                dist_por_viaje = round(distancia_km / total_viajes, 3)
                ganancia_por_viaje = round(ganancia_neta / total_viajes, 2)
                await conn.execute(
                    """
                    UPDATE viajes
                       SET distancia_gps_km        = $1,
                           ganancia_real_calculada  = $2
                     WHERE jornada_id = $3
                    """,
                    dist_por_viaje,
                    ganancia_por_viaje,
                    jornada_id,
                )

    return {
        "status": "Jornada cerrada",
        "jornada_id": str(jornada_id),
        "distancia_gps_km": round(distancia_km, 2),
        "total_ingresos": total_ingresos,
        "total_gastos": total_gastos,
        "ganancia_neta": round(ganancia_neta, 2),
        "viajes": total_viajes,
        "duracion_min": round(duracion_min, 1),
        "eficiencia_mxn_km": eficiencia,
    }


async def get_gps_historial(jornada_id: str, conductor_id: str) -> list:
    """
    Valida ownership y devuelve puntos GPS descifrados para visualización.
    Las coordenadas se descifran en memoria — nunca se persisten en claro.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM jornadas WHERE id = $1 AND conductor_id = $2",
            jornada_id, conductor_id,
        )
        if not row:
            raise ValueError("Jornada no encontrada o acceso denegado")

        gps_rows = await conn.fetch(
            """
            SELECT lat_cifrado, lng_cifrado, vel_kmh, ts
              FROM jornada_gps_logs
             WHERE jornada_id = $1
             ORDER BY ts
            """,
            jornada_id,
        )

    puntos = []
    for r in gps_rows:
        try:
            puntos.append({
                "lat": _truncar_coordenada(float(decrypt_value(bytes(r["lat_cifrado"])))),
                "lng": _truncar_coordenada(float(decrypt_value(bytes(r["lng_cifrado"])))),
                "vel_kmh": float(r["vel_kmh"]) if r["vel_kmh"] is not None else None,
                "ts": r["ts"].isoformat(),
            })
        except Exception:
            continue  # punto corrupto — saltar silenciosamente

    return puntos


async def get_resumen_jornadas_con_gps(conductor_id: str) -> list:
    """
    Devuelve metadatos de jornadas que tienen al menos un punto GPS registrado.
    Sin coordenadas — solo IDs, fechas y conteo de puntos para el selector UI.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT j.id, j.fecha, j.estado,
                   COUNT(g.id) AS total_puntos
              FROM jornadas j
              JOIN jornada_gps_logs g ON g.jornada_id = j.id
             WHERE j.conductor_id = $1
             GROUP BY j.id, j.fecha, j.estado
            HAVING COUNT(g.id) > 0
             ORDER BY j.fecha DESC
             LIMIT 30
            """,
            conductor_id,
        )
    return [
        {
            "jornada_id": str(r["id"]),
            "fecha": r["fecha"].isoformat(),
            "estado": r["estado"],
            "total_puntos": r["total_puntos"],
        }
        for r in rows
    ]


def _calcular_distancia(gps_rows) -> float:
    """
    Descifra lat/lng en memoria y calcula distancia acumulada Haversine.
    Filtra saltos imposibles (>300 km/h entre puntos consecutivos).
    """
    if len(gps_rows) < 2:
        return 0.0

    puntos = []
    for row in gps_rows:
        try:
            lat = float(decrypt_value(bytes(row["lat_cifrado"])))
            lng = float(decrypt_value(bytes(row["lng_cifrado"])))
            puntos.append((lat, lng, row["ts"]))
        except Exception:
            continue  # punto corrupto — saltar

    total_km = 0.0
    for i in range(1, len(puntos)):
        lat1, lng1, ts1 = puntos[i - 1]
        lat2, lng2, ts2 = puntos[i]
        try:
            d = geodesic((lat1, lng1), (lat2, lng2)).km
            # Filtrar saltos de teleportación (>300 km/h)
            dt_h = (ts2 - ts1).total_seconds() / 3600
            if dt_h > 0 and (d / dt_h) > 300:
                continue
            total_km += d
        except Exception:
            continue

    return total_km
