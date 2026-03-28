"""
YAGA PROJECT - Servicio de Historico de Viajes
Parsea JSONs exportados del portal Uber y los inserta en viajes_historicos.
Copyright (c) 2026 YAGA Project
"""
import re
import urllib.parse
from datetime import datetime, timezone
from typing import Optional
from services.database import get_pool


# ── Parsers de campos Uber ─────────────────────────────────────────────────────

def _parse_monto(formatted: str) -> Optional[float]:
    """'45,77 MXN' o '145.00 MXN' → float"""
    if not formatted:
        return None
    cleaned = formatted.replace("MXN", "").replace("$", "").strip()
    # Uber usa coma como decimal en Mexico
    if "," in cleaned and "." not in cleaned:
        cleaned = cleaned.replace(",", ".")
    elif "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_duracion(formatted: str) -> Optional[float]:
    """'13 min 4 seg' → 13.07  |  '1 h 30 min' → 90.0  |  '45 min' → 45.0"""
    if not formatted:
        return None
    total = 0.0
    h = re.search(r'(\d+)\s*h', formatted)
    m = re.search(r'(\d+)\s*min', formatted)
    s = re.search(r'(\d+)\s*seg', formatted)
    if h:
        total += int(h.group(1)) * 60
    if m:
        total += int(m.group(1))
    if s:
        total += int(s.group(1)) / 60
    return round(total, 2) if total > 0 else None


def _parse_distancia(formatted: str) -> Optional[float]:
    """'6.19 km' → 6.19"""
    if not formatted:
        return None
    m = re.search(r'([\d.,]+)\s*km', formatted)
    if m:
        return float(m.group(1).replace(",", "."))
    return None


def _parse_coords(map_url: str) -> tuple:
    """Extrae lat/lng del mapUrl de Uber.
    URL contiene: marker=lat%3A19.59158%24lng%3A-99.04334
    decodificado: lat:19.59158$lng:-99.04334
    """
    if not map_url:
        return None, None
    decoded = urllib.parse.unquote(map_url)
    lat_m = re.search(r'lat[=:](-?\d+\.\d+)', decoded)
    lng_m = re.search(r'lng[=:](-?\d+\.\d+)', decoded)
    if lat_m and lng_m:
        return float(lat_m.group(1)), float(lng_m.group(1))
    return None, None


# ── Normalizador principal ─────────────────────────────────────────────────────

def normalizar_viaje(raw: dict, conductor_id: str) -> Optional[dict]:
    """Normaliza un viaje crudo del JSON Uber al schema de viajes_historicos.
    Retorna None si el viaje no es COMPLETED o le falta monto.
    """
    if raw.get("type") != "TRIP" or raw.get("status") != "COMPLETED":
        return None

    meta = raw.get("tripMetaData") or {}
    lat, lng = _parse_coords(meta.get("mapUrl", ""))

    ts = raw.get("recognizedAt")
    fecha = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None

    monto = _parse_monto(raw.get("formattedTotal", ""))
    if not monto:
        return None

    dist = _parse_distancia(meta.get("formattedDistance", ""))
    dur  = _parse_duracion(meta.get("formattedDuration", ""))
    eficiencia = round(monto / dist, 2) if dist and dist > 0 else None

    return {
        "trip_id":      raw.get("uuid"),
        "conductor_id": conductor_id,
        "fecha_local":  fecha,
        "monto_bruto":  monto,
        "duracion_min": dur,
        "distancia_km": dist,
        "eficiencia_km": eficiencia,
        "plataforma":   raw.get("activityTitle", "UberX"),
        "origen":       meta.get("pickupAddress"),
        "destino":      meta.get("dropOffAddress"),
        "lat":          lat,
        "lng":          lng,
    }


# ── Operaciones DB ─────────────────────────────────────────────────────────────

async def import_viajes_json(raw_list: list, conductor_id: str) -> dict:
    """Normaliza e inserta una lista de viajes. Omite duplicados por trip_id."""
    normalizados = [v for raw in raw_list if (v := normalizar_viaje(raw, conductor_id))]

    insertados = 0
    duplicados = 0

    pool = await get_pool()
    async with pool.acquire() as conn:
        for v in normalizados:
            result = await conn.execute(
                """
                INSERT INTO viajes_historicos
                    (trip_id, conductor_id, fecha_local, monto_bruto, duracion_min,
                     distancia_km, eficiencia_km, plataforma, origen, destino, lat, lng)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                ON CONFLICT (trip_id) DO UPDATE SET
                    lat = COALESCE(viajes_historicos.lat, EXCLUDED.lat),
                    lng = COALESCE(viajes_historicos.lng, EXCLUDED.lng),
                    conductor_id = EXCLUDED.conductor_id
                """,
                v["trip_id"], v["conductor_id"], v["fecha_local"], v["monto_bruto"],
                v["duracion_min"], v["distancia_km"], v["eficiencia_km"],
                v["plataforma"], v["origen"], v["destino"], v["lat"], v["lng"],
            )
            if result == "INSERT 0 1":
                insertados += 1
            else:
                duplicados += 1

    return {
        "procesados": len(normalizados),
        "insertados": insertados,
        "duplicados": duplicados,
        "omitidos":   len(raw_list) - len(normalizados),
    }


async def get_stats_historico(conductor_id: str) -> dict:
    """Estadisticas del historico del conductor."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*)                        AS total_viajes,
                COALESCE(SUM(monto_bruto), 0)   AS ingreso_total,
                COALESCE(AVG(monto_bruto), 0)   AS promedio_viaje,
                COALESCE(AVG(distancia_km), 0)  AS distancia_promedio,
                COALESCE(SUM(distancia_km), 0)  AS distancia_total,
                MIN(fecha_local)                AS primer_viaje,
                MAX(fecha_local)                AS ultimo_viaje
            FROM viajes_historicos
            WHERE conductor_id = $1
            """,
            conductor_id,
        )
        return {
            "total_viajes":        row["total_viajes"],
            "ingreso_total":       round(float(row["ingreso_total"]), 2),
            "promedio_por_viaje":  round(float(row["promedio_viaje"]), 2),
            "distancia_promedio_km": round(float(row["distancia_promedio"]), 2),
            "distancia_total_km":  round(float(row["distancia_total"]), 2),
            "primer_viaje": str(row["primer_viaje"])[:10] if row["primer_viaje"] else None,
            "ultimo_viaje": str(row["ultimo_viaje"])[:10] if row["ultimo_viaje"] else None,
        }


async def get_mapa_data(conductor_id: str) -> list:
    """Retorna viajes con coordenadas para renderizar en el mapa del frontend."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT trip_id, fecha_local, monto_bruto, distancia_km,
                   duracion_min, plataforma, origen, lat, lng
            FROM viajes_historicos
            WHERE conductor_id = $1 AND lat IS NOT NULL AND lng IS NOT NULL
            ORDER BY fecha_local DESC
            """,
            conductor_id,
        )
        return [
            {
                "trip_id":    str(r["trip_id"])[:8],
                "fecha":      str(r["fecha_local"])[:10] if r["fecha_local"] else None,
                "monto":      float(r["monto_bruto"]),
                "distancia":  float(r["distancia_km"]) if r["distancia_km"] else None,
                "duracion":   float(r["duracion_min"]) if r["duracion_min"] else None,
                "plataforma": r["plataforma"],
                "origen":     r["origen"],
                "lat":        float(r["lat"]),
                "lng":        float(r["lng"]),
            }
            for r in rows
        ]


async def get_promedio_historico(conductor_id: str) -> float:
    """Promedio por viaje del conductor. Fallback: promedio global o $72.94."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        avg = await conn.fetchval(
            "SELECT AVG(monto_bruto) FROM viajes_historicos WHERE conductor_id = $1",
            conductor_id,
        )
        if avg:
            return round(float(avg), 2)
        global_avg = await conn.fetchval("SELECT AVG(monto_bruto) FROM viajes_historicos")
        return round(float(global_avg), 2) if global_avg else 72.94
