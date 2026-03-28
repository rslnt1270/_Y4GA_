"""
YAGA PROJECT - Servicio de Historico de Viajes
Parsea JSONs exportados de Uber y DiDi. Detecta el formato automaticamente.
Copyright (c) 2026 YAGA Project
"""
import re
import urllib.parse
from datetime import datetime, timezone
from typing import Optional
from services.database import get_pool


# ── Helpers compartidos ────────────────────────────────────────────────────────

def _to_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _parse_monto(formatted: str) -> Optional[float]:
    """'45,77 MXN' o '145.00 MXN' → float"""
    if not formatted:
        return None
    cleaned = str(formatted).replace("MXN", "").replace("$", "").strip()
    if "," in cleaned and "." not in cleaned:
        cleaned = cleaned.replace(",", ".")
    elif "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "")
    return _to_float(cleaned)


def _parse_duracion(formatted: str) -> Optional[float]:
    """'13 min 4 seg' → 13.07  |  '1 h 30 min' → 90.0"""
    if not formatted:
        return None
    total = 0.0
    h = re.search(r'(\d+)\s*h', str(formatted))
    m = re.search(r'(\d+)\s*min', str(formatted))
    s = re.search(r'(\d+)\s*seg', str(formatted))
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
    m = re.search(r'([\d.,]+)\s*km', str(formatted))
    if m:
        return _to_float(m.group(1).replace(",", "."))
    return None


def _parse_coords_uber(map_url: str) -> tuple:
    """Extrae lat/lng del mapUrl de Uber (encoded en la URL)."""
    if not map_url:
        return None, None
    decoded = urllib.parse.unquote(map_url)
    lat_m = re.search(r'lat[=:](-?\d+\.\d+)', decoded)
    lng_m = re.search(r'lng[=:](-?\d+\.\d+)', decoded)
    if lat_m and lng_m:
        return float(lat_m.group(1)), float(lng_m.group(1))
    return None, None


def _parse_timestamp(val) -> Optional[datetime]:
    """Convierte unix timestamp (int/float) o string ISO a datetime UTC."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        # DiDi a veces usa milisegundos
        if val > 1e11:
            val = val / 1000
        try:
            return datetime.fromtimestamp(val, tz=timezone.utc)
        except Exception:
            return None
    if isinstance(val, str):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                return datetime.strptime(val, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


# ── Deteccion de plataforma ────────────────────────────────────────────────────

def _detectar_plataforma(raw: dict) -> str:
    """Detecta si el viaje es de Uber o DiDi por sus keys caracteristicas."""
    keys = set(raw.keys())
    if "uuid" in keys and "recognizedAt" in keys:
        return "uber"
    if any(k in keys for k in ("orderId", "orderNo", "order_id", "orderID")):
        return "didi"
    # Fallback por contenido
    if "formattedTotal" in keys or "activityTitle" in keys:
        return "uber"
    if "driverIncome" in keys or "income" in keys:
        return "didi"
    return "uber"  # default


# ── Normalizador Uber ──────────────────────────────────────────────────────────

def _normalizar_uber(raw: dict, conductor_id: str) -> Optional[dict]:
    """Normaliza un viaje del formato Uber getWebActivityFeed."""
    if raw.get("type") != "TRIP":
        return None
    status = str(raw.get("status", "")).upper()
    if status not in ("COMPLETED", "FINISHED"):
        return None

    meta  = raw.get("tripMetaData") or {}
    lat, lng = _parse_coords_uber(meta.get("mapUrl", ""))
    fecha = _parse_timestamp(raw.get("recognizedAt"))
    monto = _parse_monto(raw.get("formattedTotal", ""))
    if not monto:
        return None

    dist = _parse_distancia(meta.get("formattedDistance", ""))
    dur  = _parse_duracion(meta.get("formattedDuration", ""))

    return {
        "trip_id":      raw.get("uuid"),
        "conductor_id": conductor_id,
        "fecha_local":  fecha,
        "monto_bruto":  monto,
        "duracion_min": dur,
        "distancia_km": dist,
        "eficiencia_km": round(monto / dist, 2) if dist and dist > 0 else None,
        "plataforma":   raw.get("activityTitle", "UberX"),
        "origen":       meta.get("pickupAddress"),
        "destino":      meta.get("dropOffAddress"),
        "lat":          lat,
        "lng":          lng,
    }


# ── Normalizador DiDi ──────────────────────────────────────────────────────────

# Estados de viaje completado en DiDi (numericos y string)
_DIDI_COMPLETED = {5, 6, "5", "6", "COMPLETED", "FINISHED", "DONE",
                   "completed", "finished", "done"}

def _normalizar_didi(raw: dict, conductor_id: str) -> Optional[dict]:
    """
    Normaliza un viaje del formato DiDi driver portal.

    DiDi no tiene un formato unico — cambia entre versiones del portal.
    Cubrimos los patrones mas comunes observados en Mexico.
    """
    # Verificar estado completado
    status = raw.get("status") or raw.get("orderStatus") or raw.get("state")
    if status not in _DIDI_COMPLETED and status is not None:
        return None

    # trip_id — varias posibles keys
    trip_id = (raw.get("orderId") or raw.get("orderNo") or
               raw.get("order_id") or raw.get("orderID") or
               raw.get("tripId") or raw.get("id"))
    if not trip_id:
        return None
    trip_id = f"didi_{trip_id}"

    # Monto — DiDi puede usar diferentes keys
    monto_raw = (raw.get("driverIncome") or raw.get("income") or
                 raw.get("price") or raw.get("fare") or
                 raw.get("totalFare") or raw.get("driverFee") or
                 raw.get("amount"))
    monto = _to_float(monto_raw)
    if not monto or monto <= 0:
        return None

    # Fecha
    ts = (raw.get("startTime") or raw.get("orderTime") or
          raw.get("createTime") or raw.get("finishTime") or
          raw.get("start_time") or raw.get("end_time"))
    fecha = _parse_timestamp(ts)

    # Distancia — DiDi puede dar metros o km
    dist_raw = (raw.get("distance") or raw.get("mileage") or
                raw.get("tripDistance") or raw.get("kilometre"))
    dist = _to_float(dist_raw)
    if dist and dist > 1000:
        dist = round(dist / 1000, 2)  # metros → km

    # Duracion — DiDi suele dar segundos
    dur_raw = (raw.get("duration") or raw.get("tripDuration") or
               raw.get("rideDuration"))
    dur = _to_float(dur_raw)
    if dur and dur > 300:
        dur = round(dur / 60, 2)  # segundos → minutos

    # Coordenadas de origen — DiDi suele dar lat/lng directos
    lat = _to_float(raw.get("latO") or raw.get("originLat") or
                    raw.get("startLat") or raw.get("lat_o") or
                    raw.get("pickupLat"))
    lng = _to_float(raw.get("lngO") or raw.get("originLng") or
                    raw.get("startLng") or raw.get("lng_o") or
                    raw.get("pickupLng"))

    # Direcciones
    origen  = (raw.get("originAddress") or raw.get("startAddress") or
               raw.get("origin_address") or raw.get("pickupAddress") or
               raw.get("fromAddress"))
    destino = (raw.get("destAddress") or raw.get("endAddress") or
               raw.get("dest_address") or raw.get("dropOffAddress") or
               raw.get("toAddress"))

    # Tipo de servicio
    plataforma = (raw.get("productType") or raw.get("orderType") or
                  raw.get("serviceType") or "DiDi Express")
    if isinstance(plataforma, int):
        plataforma = {1: "DiDi Express", 2: "DiDi Comfort", 3: "DiDi Max"}.get(plataforma, "DiDi")

    return {
        "trip_id":      str(trip_id),
        "conductor_id": conductor_id,
        "fecha_local":  fecha,
        "monto_bruto":  monto,
        "duracion_min": dur,
        "distancia_km": dist,
        "eficiencia_km": round(monto / dist, 2) if dist and dist > 0 else None,
        "plataforma":   str(plataforma),
        "origen":       origen,
        "destino":      destino,
        "lat":          lat,
        "lng":          lng,
    }


# ── Normalizador principal (auto-deteccion) ────────────────────────────────────

def normalizar_viaje(raw: dict, conductor_id: str,
                     platform: str = "auto") -> Optional[dict]:
    """
    Normaliza un viaje crudo al schema de viajes_historicos.
    platform: 'uber' | 'didi' | 'auto' (detecta automaticamente)
    """
    if not isinstance(raw, dict):
        return None

    plat = platform.lower() if platform else "auto"
    if plat == "auto":
        plat = _detectar_plataforma(raw)

    if plat == "didi":
        return _normalizar_didi(raw, conductor_id)
    return _normalizar_uber(raw, conductor_id)


# ── Operaciones DB ─────────────────────────────────────────────────────────────

async def import_viajes_json(raw_list: list, conductor_id: str,
                             platform: str = "auto") -> dict:
    """Normaliza e inserta una lista de viajes. Omite duplicados por trip_id."""
    normalizados = [v for raw in raw_list if (v := normalizar_viaje(raw, conductor_id, platform))]

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
                   duracion_min, plataforma, origen, destino, lat, lng
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
                "destino":    r["destino"],
                "lat":        float(r["lat"]),
                "lng":        float(r["lng"]),
            }
            for r in rows
        ]


async def get_ganancias_semanal(conductor_id: str) -> list:
    """Retorna ingresos agrupados por día de la semana (últimos 90 días)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                EXTRACT(DOW FROM fecha_local AT TIME ZONE 'America/Mexico_City') AS dia_semana,
                COALESCE(SUM(monto_bruto), 0) AS total,
                COUNT(*) AS viajes
            FROM viajes_historicos
            WHERE conductor_id = $1
              AND fecha_local >= NOW() - INTERVAL '90 days'
            GROUP BY dia_semana
            ORDER BY dia_semana
            """,
            conductor_id,
        )
        return [{"dia_semana": int(r["dia_semana"]), "total": round(float(r["total"]), 2), "viajes": int(r["viajes"])} for r in rows]


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
